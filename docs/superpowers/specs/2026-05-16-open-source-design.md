# QuotaMonitor 开源化重构设计 (Spec)

**Date**: 2026-05-16
**Author**: Frank
**Status**: Approved (brainstorming-skill v5.1.0 流程产出)
**Source project**: `/Users/frank/Documents/Frank/OpenClaw/QuotaMonitor`（原仓，保持运行不动）
**Target project**: `/Users/frank/Documents/Frank/OpenClaw/quota-monitor`（新仓，本 spec 所在地）

---

## 0. P0 行动项（不进 spec 范围，但必须立即处理）

原仓 `claude_status.js:35-36, 128-129` 包含**真实 Telegram Bot Token** (`7945033035:AAHX...`) 与 Chat ID。
开源前**必须先**做：

1. 去 BotFather 跑 `/revoke` 吊销现 token，重新生成。
2. 新 token 只通过 `.env` / `wrangler secret` 注入，绝不入仓。
3. 原仓的 `claude_status.js` 视为已泄露源——只要 push 过任何地方都按已泄露处理。

---

## 1. Overview

将原 `QuotaMonitor`（个人化、密钥硬编码、单一通知后端）重构为**对最终用户开箱即用**的开源工具。**绿地新仓**，原仓不动以保证现有 cron 继续运行。

### 1.1 Goals

| # | 目标 |
|---|---|
| G1 | 用户群体 = 最终用户（不是贡献者）。装上能跑，onboarding 顺滑，零依赖默认 |
| G2 | 极致可配置化：每个 probe / notifier / keepalive 都有独立开关，"全关也能跑" |
| G3 | AI-Agent friendly：README 顶部提供 prep prompt，用户的本地 AI agent 可一次性把外部依赖配齐，再跑向导 |
| G4 | Keepalive 风险显式化：默认关闭 + README §Risks 详尽 + 向导启用时再次警告 |
| G5 | 通知后端从一开始就抽象成 `Notifier` Protocol，v1 仅实现 Telegram；CF Worker 作可选高级 relay |
| G6 | 平台支持：macOS 承诺；Linux best-effort；Windows 不支持 |
| G7 | 双语 README（en 默认 + zh），CLI 通过 `locale` 配置切换 |

### 1.2 Non-goals

明确**不做**：

- 多用户 / 团队部署
- Web UI / dashboard
- 历史用量统计 / 图表
- Anthropic 官方 quota API（没有 API 之前不投入）
- Linux LaunchAgent 等价物（systemd timer 由 Linux 用户写，文档给模板即可）
- 从原 `QuotaMonitor/` 自动迁移 state（用户停旧 cron + 跑新 setup 即可）
- 自定义 keepalive prompt pool 的 GUI 编辑器（toml 文件够）

---

## 2. 决策汇总（brainstorming 阶段共识）

| # | 维度 | 决定 |
|---|---|---|
| 1 | 目标用户 | 最终用户，装上能跑 |
| 2 | Keepalive | 默认关闭 + 显式开启 + README 红警，代码保留 |
| 3 | 核心语言 | Python（保留，零运行时依赖） |
| 4 | Python 最低版本 | 3.11+（用 `tomllib` 零依赖） |
| 5 | Notifier 抽象 | 接口一开始就抽，v1 仅 telegram，CF 作可选 relay 实现 |
| 6 | 平台 | macOS 承诺 / Linux best-effort / Windows 不支持 |
| 7 | 配置 | TOML + `.env` 分离 |
| 8 | 实施方式 | 绿地重写，原 `QuotaMonitor/` 不动 |
| 9 | i18n | en（默认）+ zh，配置可切换；双份 README |
| 10 | Onboarding | 首次运行交互式向导 + 启动前 preflight checks |
| 11 | README 风格 | 紧凑列条件/步骤/效果 + AI Agent prep prompt |
| 12 | CF relay | 集成进主向导（步 5），不再做单独子命令 |
| 13 | Keepalive 调度 | `polling`（默认，cron 5min 轮询）+ `seamless`（高级，保留原 tmux 方案） |
| 14 | Keepalive 内容 | 10 条短语池随机不重复采样，内容指纹化降级 |
| 15 | 状态持久化 | `~/.quota-monitor/state.json`，atomic write |

---

## 3. 架构

### 3.1 高层图

```
[macOS launchd / cron]  ── every 5 min ──▶  python -m quota_monitor run
                                                       │
        ┌──────────────────────────────────────────────┼──────────────────────────────────────┐
        │                                              ▼                                       │
        │  ┌─────────┐    ┌──────────┐    ┌──────────────┐                                     │
        │  │ probes/ │──▶│  core/   │──▶│  notifiers/  │   (cf-relay = 高级实现,opt-in)        │
        │  │  claude │    │ window   │    │  telegram    │                                     │
        │  │  codex  │    │ state    │    │  macos_native│                                     │
        │  └─────────┘    └──────────┘    │ cf_relay     │                                     │
        │                                  └──────────────┘                                    │
        │                                                                                       │
        │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐  │
        │  │ keepalive/   │   │ cli/         │   │ platform/    │   │ config/  i18n/       │  │
        │  │ (opt-in)     │   │ setup        │   │ paths        │   │ TOML + .env loader   │  │
        │  │ phrase pool  │   │ run          │   │ schedule     │   │ en/zh messages       │  │
        │  │ + strategy   │   │ status       │   └──────────────┘   └──────────────────────┘  │
        │  └──────────────┘   │ notify-test  │                                                  │
        │                     │ uninstall    │                                                  │
        │                     └──────────────┘                                                  │
        └───────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 模块边界

| 模块 | 职责 | 对外暴露 | 依赖 |
|---|---|---|---|
| `probes/` | 从日志/API 提取活动时间戳；不做决策 | `ProbeResult(timestamps, source, extra)` | `platform.paths`, stdlib |
| `core/window.py` | 5h 窗口切分算法 + "是否要发通知"判断 | `WindowState`, `decide_alerts()` | `probes/` 的 dataclass |
| `core/state.py` | 状态持久化，atomic write，损坏自愈 | `load_state()`, `save_state()` | stdlib |
| `notifiers/` | `Notifier` Protocol + 实现 | `Notifier.send(Alert)` | stdlib HTTP |
| `keepalive/` | 续杯逻辑 + sleep-aware 调度 + phrase pool；默认禁用 | `KeepaliveStrategy.tick()` | `platform.schedule` |
| `platform/paths.py` | macOS 路径假设的唯一栖息地 | `paths.claude_app_dir`... | `os`, `platform` |
| `platform/schedule.py` | LaunchAgent plist 生成、launchctl 调用、tmux 调度 | `install_launchagent()`, `schedule_at()` | `subprocess` |
| `config/` | TOML + `.env` 装载、schema 校验 | `Config` dataclass | `tomllib`, 自写 dotenv parser |
| `i18n/` | `t(key, **kwargs)` + en/zh 字典 | `t()` | 无 |
| `cli/` | `setup` 向导、`run` 单次扫描、`status`、`notify-test`、`uninstall` | argparse entry | 上面所有 |

### 3.3 目录结构

```
quota-monitor/
├── README.md                 (英文,默认)
├── README.zh-CN.md           (简体中文,与英文同步)
├── LICENSE                   (MIT)
├── pyproject.toml            (PEP 621; 零运行时依赖)
├── config.example.toml       (入仓模板)
├── .env.example              (入仓模板)
├── .gitignore                (.env, ~/.quota-monitor/, tmp/, .DS_Store)
├── docs/
│   ├── ARCHITECTURE.md
│   ├── cloudflare.md         (CF relay 详解)
│   ├── adding-notifier.md    (贡献者指南)
│   ├── linux-systemd.md      (Linux 用户写 systemd timer 的模板)
│   └── superpowers/
│       ├── specs/
│       │   └── 2026-05-16-open-source-design.md  ← 本文件
│       └── plans/            (writing-plans 阶段产出)
├── quota_monitor/
│   ├── __init__.py
│   ├── __main__.py           (python -m quota_monitor 入口)
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── setup.py
│   │   ├── run.py
│   │   ├── status.py
│   │   ├── notify_test.py
│   │   └── uninstall.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── loader.py         (TOML + .env)
│   │   ├── schema.py         (dataclass + 校验)
│   │   └── dotenv.py         (自写 KV parser ~30 行)
│   ├── probes/
│   │   ├── __init__.py       (ProbeResult dataclass)
│   │   ├── claude.py
│   │   └── codex.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── window.py         (calculate_window_state, decide_alerts)
│   │   └── state.py          (atomic JSON IO + self-heal)
│   ├── notifiers/
│   │   ├── __init__.py       (Notifier Protocol, Alert dataclass)
│   │   ├── telegram.py
│   │   ├── macos_native.py
│   │   └── cloudflare_relay.py
│   ├── keepalive/
│   │   ├── __init__.py       (KeepaliveStrategy ABC)
│   │   ├── polling.py
│   │   ├── seamless.py
│   │   ├── activity.py       (共享 idle 判断)
│   │   ├── phrases.py        (DEFAULT_PHRASES + 不重复采样)
│   │   └── runner.py         (subprocess 执行 claude CLI)
│   ├── platform/
│   │   ├── __init__.py
│   │   ├── paths.py
│   │   └── schedule.py       (LaunchAgent plist gen, launchctl)
│   └── i18n/
│       ├── __init__.py       (t() function)
│       └── messages/
│           ├── en.py
│           └── zh.py
├── tests/
│   ├── test_window.py
│   ├── test_state.py
│   ├── test_probes.py
│   ├── test_notifiers.py
│   ├── test_keepalive.py
│   ├── test_config.py
│   ├── test_wizard_smoke.py
│   └── fixtures/
│       ├── claude-app-cache/
│       ├── cli-jsonl/
│       └── codex-auth.json   (脱敏)
├── cloudflare-relay/
│   ├── README.md
│   ├── wrangler.toml.example
│   ├── package.json
│   └── src/
│       └── worker.js         (重构原 claude_status.js, secrets 走 wrangler secret)
└── scripts/
    └── dev-setup.sh
```

---

## 4. 数据流（单次 `run` 调用）

```
1. load_config()            ── TOML + .env。schema 校验失败 → exit(1) + 提示跑 setup
2. load_state()             ── ~/.quota-monitor/state.json。损坏 → 重置 default + log warn
3. run_probes_parallel()    ── 启用的 probes 并行。单 probe 异常 → log warn,继续
        │
        ├─ ProbeResult(source="claude", timestamps=[...], extra={...})
        └─ ProbeResult(source="codex", reset_at=..., used_percent=..., ...)
4. core.window.decide()     ── 输入 (state, probe_results) → 输出 List[AlertDecision]
                                去重逻辑在此(同 reset_at 只发一次)
5. dispatch_alerts()        ── 对每条 decision 调 primary notifier
                                失败重试 3 次(1s/3s/9s) → 失败再走 fallback notifier
                                两者都失败 → 不写"已通知"标记,下次 cron 自然重试
6. (opt-in) keepalive.tick()── 主流程在 cfg.keepalive.enabled=true 时按需 import
7. save_state()             ── atomic write (写 .tmp → rename)
```

**纯函数边界**：步骤 2-7 全部输入 → 输出可测，不需要真 mock HTTP。

---

## 5. 配置 Schema

### 5.1 `config.toml`

```toml
# ~/.quota-monitor/config.toml
locale = "en"              # "en" | "zh"
log_level = "info"         # "debug" | "info" | "warn" | "error"

[probes.claude]
enabled = true
threshold_turns = 5        # 窗口内活动达此值视为"已用满"
window_hours = 5

[probes.codex]
enabled = true
threshold_percent = 30     # 5h 窗口用满多少触发

[notifiers]
primary = "telegram"       # 主通道(必填)
fallback = "macos_native"  # 主通道失败时降级;留空表示不降级

[notifiers.telegram]
# token / chat_id 走 .env,不在此

[notifiers.cloudflare_relay]
enabled = false
webhook_url = ""           # setup 向导自动填回

[keepalive]                # ⚠️ 见 README §Risks
enabled = false
strategy = "polling"       # "polling" | "seamless"
model = "haiku"
phrase_pool = []           # 空 = 用 builtin DEFAULT_PHRASES;用户可覆写为自己的列表

# 仅 strategy = "seamless" 时生效
seamless_trigger_minutes = 30  # 窗口剩多少分钟开始挂 tmux
seamless_buffer_seconds = 60   # 续杯延后 reset 多少秒
```

### 5.2 `.env`

```dotenv
# ~/.quota-monitor/.env  (gitignored)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

`.env.example` 入仓作模板,内容相同但值留空。

### 5.3 设计原则

- **默认值就是"开箱即用"的合理值**:用户不动配置也能跑(假设已配 Telegram 凭据)
- **TOML 全部可入仓**,`.env` 严格 gitignored
- **dotenv parser 自写 ~30 行**,不引第三方依赖
- 配置加载失败信息要明确指出**缺哪个字段**+**建议跑 `setup`**

---

## 6. 状态文件 Schema

> **Post-bug-fix simplification (2026-05-16)**: 原 spec 在 `claude` 块里有 `current_window_start` 和 `current_window_reset`。**已删除**。原 `monitor.py` 因为保存 `last_reset_time` 并用它过滤历史导致"saved 时间在未来时所有历史 timestamps 都被过滤掉、count=0、报警永远不触发"的死寂 bug。修复方法是**算法层面**改用 Full Replay (`replay_windows(timestamps)` — 见 plan Task 9):每次 tick 都从最早的时间戳重放整段历史得到最新窗口,state 完全不参与切分。state 只保留"哪个 reset 已经报过警"。这样原 bug 在结构上不再可能。

```json
{
  "schema_version": 1,
  "claude": {
    "alerted_for_reset": 1747368000
  },
  "codex": {
    "alerted_for_reset": 1747368000,
    "cooldown_until": 1747368000
  },
  "keepalive": {
    "last_seamless_scheduled_for": 1747368000,
    "phrase_pool_used_indices": [0, 3, 7],
    "phrase_pool_size_at_init": 10
  }
}
```

### 6.1 关键设计

- 路径 `~/.quota-monitor/state.json`,与项目目录解耦(cron 工作目录不稳)
- `schema_version` 给未来 v2 迁移留口子,v1 = 1
- **`claude.alerted_for_reset` 是 Claude 状态的唯一字段**——单一信源,跨窗口判断退化为 `state.claude.alerted_for_reset == int(latest_window.reset)`,无任何不一致空间
- 窗口起止时间**不入 state**——它们每次 tick 由 `replay_windows()` 从 probe 时间戳现算
- `phrase_pool_size_at_init` 记录用户配置时的池大小;若 `len(cfg.phrase_pool) != size_at_init` → 视为池已改,清空 used 索引重新开始
- 损坏 / 缺失 → 重置 default + log warn,绝不崩
- 并发写入 → atomic write (写 `.tmp` → `os.rename`),不上文件锁
- 向后兼容:loader 见到旧字段(`current_window_start` / `current_window_reset`)静默丢弃

---

## 7. Notifier 抽象

### 7.1 Protocol

```python
# quota_monitor/notifiers/__init__.py

from typing import Protocol
from dataclasses import dataclass

@dataclass(frozen=True)
class Alert:
    title: str            # i18n-resolved
    body: str             # i18n-resolved, may contain markdown
    reset_at: int         # epoch seconds; relays use this to schedule
    source: str           # "claude" | "codex"

class Notifier(Protocol):
    name: str             # "telegram" | "macos_native" | "cloudflare_relay"

    def send(self, alert: Alert) -> None:
        """成功返回 None;失败抛 NotifierError(下含原因 + 是否值得重试)"""
        ...

class NotifierError(Exception):
    retryable: bool       # True = 网络抖动;False = 凭据错等永久错误
```

### 7.2 v1 实现

| 实现 | 适用场景 | 关键行为 |
|---|---|---|
| `telegram` | 默认主通道 | HTTP POST 到 Bot API,凭据来自 .env |
| `macos_native` | fallback / 在电脑前 | `osascript -e 'display notification ...'`,即时不可延迟 |
| `cloudflare_relay` | 用户想电脑关机也准时收 | HTTP POST 到自己部署的 Worker,Worker 用 KV + cron 定时发 |

### 7.3 失败 / 降级

- `send()` 抛 retryable error → 调用方按 1s/3s/9s 指数重试 3 次
- 重试用尽 → 调 `fallback notifier`(如配置)
- fallback 也失败 → log error,状态不写已通知,下次 cron tick 重试

---

## 8. Keepalive 设计

### 8.1 Strategy

|  Strategy | 行为 | 调度恢复(睡眠醒后) | 业务效果(整夜睡眠) |
|---|---|---|---|
| `polling`(默认) | cron 每次 tick 检查"是否已过 reset 或距 reset < poll_interval",已过 → 立即续 | ✅ launchd 醒后立即触发下次 tick | ❌ 睡眠期已自然 reset 的窗口救不回 |
| `seamless`(高级) | 窗口剩 ≤30 分钟时挂 tmux + sleep,reset 后 +60s 续杯 | ❌ macOS sleep 时单调时钟停,挂起的 tmux 倒计时被推迟 | ❌ 同上 + 倒计时错位 |

两列含义:
- **调度恢复**:电脑醒来后,调度机制本身能不能继续工作。polling 走 launchd 重新触发,seamless 走 `tmux sleep N` 本身被睡眠暂停。
- **业务效果**:无论调度是否恢复,睡眠期内已经过了 reset 时刻的窗口已经被 Anthropic 那边自然 reset,本地续杯救不回。

### 8.2 Sleep 限制(必须告知用户)

**业务效果维度上,两种 strategy 在 macOS 整机 sleep(合盖 / idle sleep)期间都救不回已经 reset 的窗口**——续杯命令必须在本机跑,系统挂起期间无法执行;醒来后那个窗口的自然 reset 已发生。
**README §Risks 与向导步 6 必须明示**:"若 MacBook 夜里 sleep,窗口会自然 reset,keepalive 救不回。"

### 8.3 Phrase Pool

```python
# quota_monitor/keepalive/phrases.py

DEFAULT_PHRASES = [
    "hi", "hello", "hey", "yo", "thanks",
    "morning", "你好", "嗨", "👋", "ok",
]
```

**采样算法**:
1. `pool = cfg.phrase_pool or DEFAULT_PHRASES`
2. 若 `state.phrase_pool_size_at_init != len(pool)` → 重置 used = [], size_at_init = len(pool)
3. `available = [i for i in range(len(pool)) if i not in used]`
4. `i = random.choice(available)`
5. `used.append(i)`; 若 `len(used) == len(pool)` → `used = []`(下一轮)
6. 返回 `pool[i]` 作 keepalive 消息

**诚实评估(写入 README §Risks)**:
phrase pool 仅消除"消息内容 = `hi`"这一弱信号;**不能规避基于模式的检测**(请求时序、token 总量、单次会话无上下文、模型选择等)。

### 8.4 续杯命令

```python
cmd = f'{shell_path} -lc "{claude_cli_path} -p \'{phrase}\' --model {model} --no-session-persistence"'
```

- `shell_path`、`claude_cli_path` 由 setup 向导探测一次写入 config,**runtime 不依赖 PATH**
  (原项目 hardcode `$HOME/.local/bin:$HOME/.n/bin` 是反模式,因为 cron 跑时 PATH 是裸的)
- 成功/失败都 log,失败不重试(下次 cron tick 自然重试)

---

## 9. CLI 命令

```bash
python -m quota_monitor setup            # 交互式向导(首次)
python -m quota_monitor run              # 单次扫描(cron / launchd 调用)
python -m quota_monitor run --dry-run    # 不发通知不写状态,全程 log
python -m quota_monitor status           # 当前窗口、上次报警、keepalive 状态
python -m quota_monitor notify-test      # 给每个 enabled notifier 发测试消息
python -m quota_monitor notify-test --backend telegram    # 指定单个
python -m quota_monitor uninstall        # 卸 LaunchAgent + 提示手删 config/state
```

向导用 stdlib `input()` + 简单 ANSI 颜色实现,不引 `questionary` 等。

---

## 10. Onboarding 向导

### 10.1 Preflight Checks(向导第一步)

```
[Preflight]
  Python ≥ 3.11               ✓ 3.12.1
  `claude` CLI                ✓ /Users/frank/.local/bin/claude
  `wrangler` CLI              ✓ 3.78.0  (会进一步 `wrangler whoami` 若选 CF)
  `~/.quota-monitor/.env`     ✓ 2 keys present
  `~/.codex/auth.json`        ✓ found  (codex probe ready)

⚠️ 缺东西? 退出向导跑 README 的 Prep prompt 让 AI agent 补齐,再重跑。
```

**关键 UX**:**禁止向导中途暂停去装东西**。所有外部依赖在向导启动前一次性 check 完。

### 10.2 步骤(7 步)

| 步 | 内容 |
|---|---|
| 1 | Language: English / 中文 |
| 2 | Services to monitor: [✓] Claude [✓] Codex(多选) |
| 3 | Primary notifier: [1] Telegram direct [2] macOS native [3] Telegram via CF relay |
| | Fallback: [1] macOS native [2] none |
| 4 | Telegram credentials(从 .env 探测,确认或重输;send test message) |
| 5 | (仅步 3 选了 [3] CF)Cloudflare relay 部署: |
| | `wrangler whoami` → KV namespace 创建 → secrets push → `wrangler deploy` → webhook_url 写回 |
| 6 | Keepalive(⚠️ 显示 ToS + sleep 双警告;默认 N) |
| | 若 Y → strategy 选择 [1] polling [2] seamless |
| 7 | Schedule install: [1] LaunchAgent(默认) [2] crontab line 打印手贴 [3] skip |

### 10.3 向导生成的产物

- `~/.quota-monitor/config.toml`
- `~/.quota-monitor/.env`(若步 4 重输新值)
- `~/Library/LaunchAgents/io.github.<repo>.quotamonitor.plist`(若步 7 选 1)
- `cloudflare-relay/wrangler.toml`(若步 5 部署 CF)

---

## 11. README 结构

### 11.1 顶级章节

```markdown
# QuotaMonitor

> [tagline 一行]

[badges]

## Setup with your AI Agent (recommended)   ← 用户 share GitHub 链接的第一个落点
## Quickstart (manual)                       ← 不用 AI agent 的备选
## What it does
## How it works (in 30 seconds)              ← 实现原理简述
## Safety & privacy                          ← 开源 / 本地 / 凭据本地 / 不读内容
## Cost                                      ← 本地零成本 + CF 免费层数学
## Choose your notification channel          ← 表格 + 决策建议
## Adding a channel we don't support         ← "复制此 prompt 给 AI"
## Advanced: Cloudflare relay                ← 详细 link 到 docs/cloudflare.md
## ⚠️ Risks                                  ← Keepalive ToS + sleep 限制 + phrase pool 诚实评估
## Platform support
## Troubleshooting
## Architecture
## License
```

### 11.2 「AI Agent Prep Prompt」(README 第一节核心内容)

```markdown
## Setup with your AI Agent (recommended)

This tool assumes you have a local AI agent (Claude Code / Codex / 
Gemini CLI / OpenClaw / Hermes). The smoothest path is to let it 
prepare the outside world before you run the wizard.

### Step 1 — Paste this prompt to your AI agent:

> I want to install QuotaMonitor (https://github.com/<repo>) on macOS.
> Read its README and prepare ALL prerequisites so the setup wizard
> runs from start to finish without interruption:
>
> 1. **Python ≥ 3.11**.  If missing: `brew install python@3.12`
> 2. **`claude` CLI** in PATH (only if I plan to enable keepalive).
> 3. **Telegram bot**: create via @BotFather, get token + chat_id, 
>    write them to `~/.quota-monitor/.env` using `.env.example`.
> 4. **Cloudflare relay** (recommended if I'm a developer):
>    - `npm install -g wrangler`
>    - `wrangler login`  (opens browser; I'll authenticate)
>    - Confirm `wrangler whoami` returns my account.
> 5. **Read README §Risks** with me — decide if I enable keepalive.
> 6. **Decide** schedule install: LaunchAgent (default) or manual cron.
>
> When prerequisites are ready, tell me to run:
>     python3.11 -m quota_monitor setup

### Step 2 — Run the wizard
    python3.11 -m quota_monitor setup

### Security note
If you give your AI agent a Cloudflare API token, use a **scoped 
token** (Workers + KV only), not your Global API Key. Revoke after.
```

### 11.3 双语策略

- `README.md` 英文,作 default
- `README.zh-CN.md` 简体中文,顶部加 `English | [中文]` 切换链接
- 两份**手工保持同步**,CONTRIBUTING 明示责任
- 内容结构、章节顺序、prompt 文本等同

### 11.4 §Risks 章节(精确措辞)

```markdown
## ⚠️ Risks

### Keepalive (auto-renew Claude 5h window)
- **Default: off.**
- **ToS**: Anthropic's AUP discourages automated usage. Enable at 
  your own risk; at scale this may invite attention or risk your account.
- **Sleep limitation**: keepalive **stops working** while macOS sleeps 
  (lid closed / idle sleep). Both `polling` and `seamless` strategies 
  fail under sleep. The natural 5h reset will still happen — keepalive 
  cannot save it.
- **Workarounds**: desktop / always-on machine, `caffeinate -i`, or 
  accept the natural reset.

### Keepalive content randomization — what it does and doesn't
We randomize keepalive content from a 10-phrase pool so no single 
message appears more than once per 10 keepalives. This neutralizes 
content-keyword detection.

**It does NOT defeat pattern-based detection** — request timing, token 
volume, session shape, and model choice are stronger signals than content. 
Use keepalive understanding any automated keep-window-alive behavior is 
detectable in principle.

### Secret leak
- Never commit `.env`. Rotate Telegram tokens via @BotFather if leaked.
```

---

## 12. 错误处理矩阵

| 故障 | 期望 | 不期望 |
|---|---|---|
| Probe 失败 | warn log,其他 probe 继续 | 整 run 退出 |
| Probe 数据损坏 | 跳过该文件,debug log | 崩 |
| 配置缺失 / schema 校验失败 | exit(1) + 明确字段 + 建议 `setup` | 用默认值偷偷继续 |
| 状态文件损坏 | 重置 default + warn log | 崩 |
| Notifier 失败 | 重试 3 次(1s/3s/9s)→ fallback | 静默丢通知 |
| Fallback 也失败 | error log + **不**写已通知 | 写已通知导致丢失 |
| Keepalive 子命令失败 | error log,下次 cron 自然重试 | 重试循环 |
| `wrangler deploy` 失败(仅 setup) | 报错 + 文档链接 + 回滚 config 的 cf 配置 | 留半残状态 |
| CF Worker schedule POST 失败 | 本地 warn,状态不写已排期,下次 cron 重试 | 重复发送 |
| LaunchAgent 加载失败 | 提示手动 `launchctl load -w` + 文档链接 | 静默成功 |

**通用原则**:
- 错误不静默——所有 catch 必须 log(默认 stderr,cron 重定向到 `~/.quota-monitor/quota-monitor.log`,自动 rotate 10MB × 3 份)
- 状态机要永远可恢复——任何崩溃不应让下次 cron 跑不出来
- 去重不依赖网络——已通知标记只在 notifier 成功返回后才写状态

---

## 13. 测试策略

不追覆盖率指标,追"换实现也能通过"。

| 类型 | 范围 | 工具 |
|---|---|---|
| 单元 | `core.window`、`config.loader`、`state` atomic IO、`platform.paths`、`i18n.t`、`keepalive.phrases` | `pytest` |
| 集成(fixture-based) | 喂一组 jsonl/json fixture → 跑完整 `run()` → 断言 state + notify call | `pytest` + dummy Notifier |
| Notifier contract | 每个 Notifier 跑同组 Protocol 测试(send / fail / retry) | `pytest` parametrize |
| Wizard smoke | `setup --non-interactive --answers test_answers.json` 一键跑完 | `pytest` |
| 手测清单 | 真发 Telegram、真 `wrangler deploy`、真 `launchctl load` — CI 不跑,发布前人工跑 | checklist in CONTRIBUTING.md |

**核心单测必含**:
- `calculate_window_state`:原 3 case + 空 list + 单条恰好等于 last_reset + 跨日 timezone
- `decide_alerts`:首次满阈值、已通知过、新窗口激活、跨窗口
- atomic write:写一半被 kill → 旧状态完整不损坏
- phrase pool:满 10 次后 used 自动清空、修改 pool size 触发重置

---

## 14. v1 验收清单

- [ ] 全新 macOS(无任何 dotfile)跑 `setup` → 5 分钟内首个测试通知到 Telegram
- [ ] 全新 macOS 跑 `setup` 选 CF → `wrangler deploy` 成功 + KV 创建 + webhook_url 写回 config
- [ ] 模拟 5 轮对话写入 fixture → `run --dry-run` 报告 "would alert at <reset_time>"
- [ ] `run` 跑两次:第一次发通知,第二次同窗口静默
- [ ] keepalive=true + idle 5h → `claude -p <随机短语>` 实际执行(验证日志含 phrase 字段)
- [ ] 配置文件故意删一项 → `run` exit != 0 + 明确报错
- [ ] state.json 故意写损坏 → `run` 自愈 + warn 日志
- [ ] LaunchAgent 安装后重启 Mac → 5 分钟内首个 cron 触发
- [ ] README "AI Agent Prep prompt" 给 Claude Code 跑一遍 → agent 能独立完成 prep(人工评估)
- [ ] `notify-test` 对每个 enabled backend 都成功发出
- [ ] phrase pool 跑 11 次 keepalive → 验证前 10 次 phrase 不重复,第 11 次进入新轮
- [ ] README.md 与 README.zh-CN.md 章节顺序与内容点位完全一致(人工对比)

---

## 15. 实施路径(此处仅枚举,详细 plan 由 writing-plans skill 出)

后续由 `writing-plans` skill 把以下分解成细颗粒度 TDD 任务:

1. 仓骨架 + `pyproject.toml` + `pytest` 跑通空测试
2. `config.loader` + `dotenv` 自写 parser + 单测
3. `core.state` atomic IO + 自愈 + 单测
4. `probes.claude` + `probes.codex` + fixture 测试
5. `core.window` 算法移植 + 增强单测
6. `notifiers` Protocol + telegram 实现 + macos_native + contract 测试
7. `keepalive` polling + phrases + 单测
8. `keepalive` seamless(移植原 tmux 逻辑)+ 单测
9. `cli.run` 主流程拼装 + dry-run + 集成测试
10. `platform.schedule` LaunchAgent plist 生成
11. `cli.setup` 向导(preflight + 步 1-4 + 步 7)
12. `cli.setup` CF relay 集成(步 5)+ `cloudflare-relay/` 重构
13. `cli.status` / `notify-test` / `uninstall`
14. `i18n` en + zh 字典补全
15. README.md + README.zh-CN.md 双语撰写
16. docs/ 子文档(ARCHITECTURE / cloudflare / adding-notifier / linux-systemd)
17. CONTRIBUTING + LICENSE + 验收清单全部跑通

---

## 16. 开放问题(后续 plan 阶段确认)

- LaunchAgent label 字符串里的 `<repo>` 待 GitHub repo 名定名后回填(候选: `quota-monitor` / `quotamonitor`)
- `pyproject.toml` 是否 publish 到 PyPI 让 `pip install quota-monitor` 一行装 — v1 暂不,先走 `git clone` + `python -m`,降低用户预期阻力
- Linux best-effort 的下限边界:监控 + Telegram 跑通即可;keepalive 默认 polling(systemd timer 5min),无 seamless
