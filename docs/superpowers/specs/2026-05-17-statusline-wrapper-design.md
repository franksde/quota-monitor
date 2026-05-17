# StatusLine Wrapper — 精确用量追踪设计

> **目标**: 通过 Claude Code statusLine 机制获取精确的 5h/7d 额度百分比和 reset 时间，与现有本地文件重放估算系统融合，并动态校准校正常数。

## 1. 架构概览

```
Claude Code stdin JSON
       │
       ▼
┌─────────────────────┐
│ statusline/wrapper   │ ← python -m quota_monitor.statusline
│  1. parse rate_limits│
│  2. atomic write cache│
│  3. exec original cmd│
│  4. pipe stdout back │
└─────────────────────┘
       │
       ▼ (缓存文件)
~/.quota-monitor/rate_limits_cache.json
       │
       ▼ (定时读取)
┌─────────────────────┐
│ run_once             │
│  精确值 > 估算回退   │
│  + 校准采样          │
└─────────────────────┘
```

核心原则：
- **Fail-open**: wrapper 任何步骤失败都不影响 Claude Code 正常使用
- **低侵入**: 只改 `~/.claude/settings.json` 的 statusLine 字段，完整备份原值
- **单一职责**: wrapper 只做截取+转发，决策逻辑留在 run_once

## 2. StatusLine Wrapper

### 2.1 入口

- 文件: `quota_monitor/statusline/wrapper.py`
- 调用方式: `python3 -m quota_monitor.statusline`
- 生命周期: one-shot command，每次 Claude Code 状态更新时被 spawn 一次

### 2.2 执行流程

```python
def main():
    raw = sys.stdin.read()

    # Step 1: 截取 rate_limits（容错）
    try:
        data = json.loads(raw)
        rate_limits = data.get("rate_limits")
        if rate_limits:
            write_cache(rate_limits)  # 原子写
    except Exception:
        pass  # fail-open

    # Step 2: 调用原始 command
    original = load_original_command()
    if original:
        try:
            result = subprocess.run(
                original, input=raw, capture_output=True,
                text=True, timeout=5
            )
            sys.stdout.write(result.stdout)
        except Exception:
            pass  # 原始 command 失败 → 输出空
```

### 2.3 缓存写入

- 路径: `~/.quota-monitor/rate_limits_cache.json`
- 原子写: 写 `.tmp` 文件后 `os.replace()`
- 格式:

```json
{
  "captured_at": 1738425000,
  "five_hour": {
    "used_percentage": 23.5,
    "resets_at": 1738425600
  },
  "seven_day": {
    "used_percentage": 41.2,
    "resets_at": 1738857600
  }
}
```

### 2.4 原始 command 的存储与调用

- 备份文件: `~/.quota-monitor/statusline_original.json`
- 内容: 原始 statusLine 配置的完整值（object 或 string 或 null）

```json
{
  "original": {
    "type": "command",
    "command": "~/.open-island/bin/open-island-statusline",
    "refreshInterval": 5
  }
}
```

- 加载时: 从 `original` 中提取 command 字符串
  - object 形态 → 取 `.command` 字段
  - string 形态 → 直接使用
  - null/missing → 无原始命令，跳过转发

### 2.5 性能约束

- 只导入 stdlib: `json`, `sys`, `subprocess`, `os`, `time`
- 不导入 quota_monitor 的其他模块（config, notifiers, probes 等）
- 目标: < 50ms 总执行时间
- 不做网络请求

## 3. 精确值探针 (Precise Probe)

### 3.1 文件

`quota_monitor/probes/precise.py`

### 3.2 接口

```python
@dataclass(frozen=True)
class PreciseUsage:
    five_hour_pct: float          # 0.0 - 100.0
    five_hour_resets_at: float    # epoch seconds
    seven_day_pct: float          # 0.0 - 100.0
    seven_day_resets_at: float    # epoch seconds
    captured_at: float            # epoch seconds

def read_precise(cache_path: Path, now: float) -> Optional[PreciseUsage]:
    """读取缓存，返回精确值。如果缓存不存在、解析失败、或 five_hour 已过期返回 None。"""
```

### 3.3 过期判断

- `five_hour.resets_at > now` → 未过期，返回 PreciseUsage
- `five_hour.resets_at <= now` → 已过期，返回 None
- `captured_at` 距 now 超过 6 小时 → 返回 None（防止僵尸缓存）

## 4. 精确/估算决策逻辑

在 `cli/run.py` 的 `run_once` 中：

```
precise = read_precise(cache_path, now)

if precise is not None and precise.five_hour_resets_at > now:
    # 精确模式：直接使用 statusLine 提供的值
    claude_reset_at = precise.five_hour_resets_at
    claude_used_pct = precise.five_hour_pct
    source_type = "precise"
else:
    # 估算模式：使用 replay_windows + 校正常数
    claude_window = replay_windows(timestamps, correction=current_correction)
    if claude_window and claude_window.reset > now:
        claude_reset_at = claude_window.reset
        source_type = "estimated"
    else:
        # 无活跃窗口
        claude_reset_at = None
        source_type = None
```

### 4.1 通知文案区分

- `source_type == "precise"`:
  - EN: `"Quota resets at {time}"`
  - ZH: `"额度将于 {time} 恢复"`
- `source_type == "estimated"`:
  - EN: `"Quota resets at {time} (estimated from local conversation logs)"`
  - ZH: `"额度将于 {time} 恢复（根据本地对话记录时间估算）"`

### 4.2 七日窗口

- 只有精确值可用时显示（本地无法估算 7d 滚动窗口）
- `seven_day` 过期后不显示

### 4.3 时区

- 所有面向用户的时间显示使用本机时区
- 内部存储和计算一律使用 epoch seconds
- 格式化: `datetime.fromtimestamp(epoch).strftime("%H:%M")` (自动使用本机时区)

## 5. 动态校准系统

### 5.1 文件

`quota_monitor/core/calibration.py`

### 5.2 持久化

路径: `~/.quota-monitor/calibration.json`

```json
{
  "default_correction_seconds": -360,
  "current_correction_seconds": -340,
  "ema_alpha": 0.3,
  "samples": [
    {
      "ts": 1738425000,
      "precise_reset": 1738425600,
      "computed_reset": 1738425950,
      "drift": -350
    }
  ]
}
```

### 5.3 采样条件

每次 `run_once` 执行时，同时满足以下条件才采样：

1. `rate_limits_cache` 中有未过期的精确 `five_hour.resets_at`
2. `replay_windows` 能算出当前窗口（`computed_window.reset > now`）
3. 两者描述同一个窗口: `|precise_reset - computed_reset| < 1800s`（30 分钟）

### 5.4 EMA 算法

```python
def compute_correction(samples: list[Sample], alpha: float, default: float) -> float:
    if len(samples) < 3:
        return default

    # 过滤异常值: |drift| > 1800s 的样本不纳入
    valid = [s for s in samples if abs(s.drift) <= 1800]
    if len(valid) < 3:
        return default

    # EMA: 从最旧到最新遍历，越新权重越高
    ema = valid[0].drift
    for s in valid[1:]:
        ema = alpha * s.drift + (1 - alpha) * ema
    return ema
```

### 5.5 样本管理

- 最多保留 20 条
- 超过时裁剪最旧的
- `|drift| > 1800s` 标记为 outlier，不参与 EMA 计算但仍存储（供 debug）

### 5.6 window.py 修改

```python
RESET_CORRECTION_SECONDS = -360  # 默认 -6 分钟（从 -300 改为 -360）

def replay_windows(
    timestamps: tuple[float, ...],
    correction: Optional[float] = None,
) -> Optional[LatestWindow]:
    # ... 现有逻辑 ...
    actual_correction = correction if correction is not None else RESET_CORRECTION_SECONDS
    return LatestWindow(start=start, reset=reset + actual_correction, count=count)
```

## 6. Setup Wizard 集成

### 6.1 新增步骤

在现有向导最后一步之前插入：

```
=== (N/N) StatusLine 精确用量追踪 ===
```

### 6.2 检测逻辑

按优先级读取 Claude Code 配置:
1. 当前项目 `.claude/settings.local.json`
2. 当前项目 `.claude/settings.json`
3. 全局 `~/.claude/settings.json`

解析 `statusLine` 字段（兼容 object 和 string）。

### 6.3 三种情况的提示

| 情况 | EN | ZH |
|------|----|----|
| 无 statusLine | "Enable statusLine usage tracking? A lightweight script will read real-time quota data from Claude Code." | "是否启用 StatusLine 精确用量追踪？将配置一个轻量脚本读取 Claude Code 的实时额度信息。" |
| 已有自定义 | "Detected custom status line tool (`{cmd_preview}`). Allow wrapping it to capture precise quota data? (Your existing tool's display will not be affected)" | "检测到已安装自定义状态栏工具（`{cmd_preview}`）。是否同意包装一层以获取精确用量信息？（不会影响现有状态栏工具的显示效果）" |
| 已是 wrapper | "StatusLine wrapper already configured. Skipping." | "StatusLine wrapper 已配置，跳过。" |

### 6.4 安装动作

1. 备份当前 statusLine 完整值 → `~/.quota-monitor/statusline_original.json`
2. 修改 `~/.claude/settings.json` 的 statusLine:
   ```json
   {
     "type": "command",
     "command": "python3 -m quota_monitor.statusline",
     "refreshInterval": 5,
     "padding": <保留原值>,
     "hideVimModeIndicator": <保留原值>
   }
   ```
3. 判断"已是 wrapper": command 包含 `quota_monitor.statusline`

## 7. 卸载安全还原

### 7.1 逻辑

```
1. 读取当前 ~/.claude/settings.json（完整 JSON）
2. 检查 statusLine.command 是否包含 "quota_monitor.statusline"
   ├─ YES:
   │   读取 statusline_original.json
   │   仅替换 settings.json 的 "statusLine" 字段为备份值
   │   如果备份值为 null → 删除 statusLine 字段
   │   其余字段不动
   │
   └─ NO:
       提示 "StatusLine has been manually changed. Skipping restore."
       不修改 statusLine
3. 删除:
   - ~/.quota-monitor/rate_limits_cache.json
   - ~/.quota-monitor/statusline_original.json
   - ~/.quota-monitor/calibration.json
```

### 7.2 卸载提示

```
EN: ✓ StatusLine wrapper removed. Original status line restored.
    To verify: cat ~/.claude/settings.json | jq .statusLine

ZH: ✓ StatusLine wrapper 已移除，原状态栏配置已恢复。
    检查命令: cat ~/.claude/settings.json | jq .statusLine
```

## 8. 新增/修改文件清单

### 新增

| 文件 | 说明 |
|------|------|
| `quota_monitor/statusline/__init__.py` | 空 |
| `quota_monitor/statusline/__main__.py` | `python -m quota_monitor.statusline` 入口 |
| `quota_monitor/statusline/wrapper.py` | 核心 wrapper 逻辑 |
| `quota_monitor/statusline/installer.py` | 安装/卸载 statusLine 配置 |
| `quota_monitor/core/calibration.py` | EMA 校准算法 + calibration.json 读写 |
| `quota_monitor/probes/precise.py` | 读取 rate_limits_cache.json |
| `tests/test_statusline_wrapper.py` | wrapper stdin/stdout 管道 |
| `tests/test_calibration.py` | EMA 算法、异常值、截断 |
| `tests/test_precise_probe.py` | 缓存读取、过期判断 |
| `tests/test_statusline_installer.py` | 安装/卸载/冲突检测 |

### 修改

| 文件 | 变更 |
|------|------|
| `core/window.py` | 默认 correction 改 -360; replay_windows 接受 correction 参数 |
| `cli/run.py` | 集成精确/估算决策 + 校准采样 |
| `cli/setup.py` | 新增 statusLine 向导步骤 |
| `cli/uninstall.py` | 新增安全还原 statusLine |
| `i18n/messages/en.py` | `wizard.statusline.*`, `uninstall.statusline.*`, `alert.suffix.estimated` |
| `i18n/messages/zh.py` | 同上中文 |
| `platform/paths.py` | 新增 `rate_limits_cache()`, `calibration_file()`, `statusline_original()`, `claude_settings_file()` |
| `README.md` | 新增 StatusLine 精确追踪章节 |
| `README.zh-CN.md` | 同上中文 |

## 9. 不做的事情

- **不抓 cookie/token**: 只使用 Claude Code 主动推送给 statusLine 的公开数据
- **不上传数据**: 所有数据留在本地 `~/.quota-monitor/`
- **不保存 prompt**: wrapper 只提取 `rate_limits` 字段，不存储 stdin 中的其他内容
- **不估算 7d 窗口**: 本地文件无法推算 7 天滚动窗口，只在精确值可用时展示
- **不添加外部依赖**: wrapper 纯 stdlib
