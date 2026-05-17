> English | [简体中文](#)

[切换语言: [English](README.md) | 中文]

# QuotaMonitor

> 监控 Claude / Codex 的 5 小时 quota 窗口，并在重置时通知你。零运行时依赖 Python，可选 Cloudflare relay。

## 用你的 AI Agent 做安装准备（推荐）

这个工具假设你有本地 AI agent（Claude Code / Codex / Gemini CLI / OpenClaw / Hermes）。最顺滑的安装方式，是先让 agent 帮你把外部依赖准备好，然后再运行向导。

### 第 1 步：把这段 prompt 发给你的 AI Agent

> 我想在 macOS 上安装 QuotaMonitor（https://github.com/<repo>）。
> 请阅读它的 README，把所有前置条件准备好，让 setup 向导可以从头到尾顺利跑完：
>
> 1. **Python ≥ 3.11**。如果没有，运行：`brew install python@3.12`
> 2. **`claude` CLI** 在 PATH 中（只有我要启用 keepalive 时才需要）。
> 3. **Telegram bot**：通过 @BotFather 创建 bot，拿到 token 和 chat_id，
>    参考 `.env.example` 写入 `~/.quota-monitor/.env`。
> 4. **Cloudflare relay**（开发者推荐开启）：
>    - `npm install -g wrangler`
>    - `wrangler login`（会打开浏览器，我来完成登录授权）
>    - 确认 `wrangler whoami` 能返回我的 Cloudflare 账号。
>    - Cloudflare Worker cron 默认保持 `*/3 * * * *`，除非我明确想改成更频繁的轮询。
> 5. **和我一起阅读 README 的风险部分**，再决定是否启用 keepalive。
> 6. **确认调度方式**：LaunchAgent（默认）或手动 cron。
>
> 前置条件准备好后，告诉我运行：
>     python3.11 -m quota_monitor setup

### 第 2 步：运行向导
    python3.11 -m quota_monitor setup

### 安全提醒
如果你把 Cloudflare API token 交给 AI agent，请使用 **scoped token**（仅 Workers + KV），不要使用 Global API Key。用完后建议撤销。

## StatusLine 精确用量追踪（可选）

quota-monitor 可以通过 Claude Code 的 [statusLine](https://docs.anthropic.com/en/docs/claude-code/status-line) 机制直接读取实时额度数据，获取精确的 5 小时和 7 天使用百分比及重置时间。

### 工作原理

1. 配置向导会将一个轻量 Python wrapper 设置为你的 Claude Code statusLine 命令
2. 每次 Claude Code 更新状态栏时，wrapper 会：
   - 从 JSON 数据中提取 `rate_limits`
   - 写入本地缓存（`~/.quota-monitor/rate_limits_cache.json`）
   - 将所有内容转发给原始 statusLine 工具（如有）
   - 原样返回原始输出
3. quota-monitor 定时扫描时，优先检查缓存：
   - **缓存有效** → 使用精确值（确切百分比和重置时间）
   - **缓存过期** → 回退到本地文件重放估算

### 兼容性

wrapper 可与现有 statusLine 工具共存：
- **Open Island** — 自动检测并包装
- **Claude HUD** — 自动检测并包装
- **ccstatusline** — 自动检测并包装
- **自定义脚本** — 任何现有 `statusLine` 配置均会保留

### 手动安装/卸载

```bash
# 安装（也可通过 `quota-monitor setup` 完成）
quota-monitor statusline install

# 卸载（也包含在 `quota-monitor uninstall` 中）
quota-monitor statusline uninstall
```

### 精确值 vs 估算值通知

- 精确值（来自 statusLine）：当 `five_hour.used_percentage` 达到 `probes.claude.precise_threshold_percent`（默认 `30`）时触发，并使用 statusLine 的精确 reset 时间：「额度将于 15:30 恢复」
- 估算值（来自本地日志）：「额度将于 15:30 恢复（根据本地对话记录时间估算）」

## 快速开始（手动）

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
mkdir -p ~/.quota-monitor
cp config.example.toml ~/.quota-monitor/config.toml
cp .env.example ~/.quota-monitor/.env
$EDITOR ~/.quota-monitor/.env
.venv/bin/python -m quota_monitor notify-test
.venv/bin/python -m quota_monitor run --dry-run
```

通过 `python3.11 -m quota_monitor setup` 安装 LaunchAgent，或使用 `docs/linux-systemd.md` 里的 Linux systemd 模板。

## 它做什么

QuotaMonitor 扫描本地 Claude 活动日志和 Codex 使用量元数据，推导当前 quota 窗口，并在重置可用时发送通知。它只保存很小的状态标记，例如“这个 reset 已经通知过”，不会保存对话内容。

可选功能：

- Telegram direct 通知。
- macOS native notification fallback。
- Cloudflare relay，用于笔记本睡眠或关机时的延迟通知。
- Claude keepalive 策略，默认关闭。

## 30 秒理解工作流程

1. `load_config()` 读取 TOML + `.env`。Schema 校验失败时退出，并给出明确 setup 提示。
2. `load_state()` 读取 `~/.quota-monitor/state.json`。损坏时重置为默认状态并记录 warning。
3. 启用的 probes 收集时间戳或用量元数据。单个 probe 失败只记录 warning，其余继续。
4. `core.window.replay_windows()` 只根据时间戳推导最新 5 小时窗口。State 不参与窗口切分。
5. `decide_alerts()` 只为尚未通知过的 reset point 产生 alert decision。
6. `dispatch_alert()` 带重试发送到 primary notifier，然后 fallback。只有 notifier 成功后才更新 state。
7. 只有显式启用时，才运行可选 keepalive 逻辑。

## 安全与隐私

- 零运行时依赖：仅使用 Python stdlib。
- Local-first：配置、密钥和状态都在 `~/.quota-monitor/`。
- 密钥放在 `.env` 或 Cloudflare Worker secrets，绝不应提交入仓。
- Claude probe 读取本地文件里的元数据和时间戳，不上传对话内容。
- Cloudflare relay 是可选功能。启用后，只会把计划发送的 alert payload 发到你自己的 Worker。

## 成本

- 本地模式成本为 $0。
- Telegram Bot API 对正常个人使用免费。
- Cloudflare relay 使用 Workers + KV。Workers 免费层是 100k requests/day；Workers KV 免费层是 100k reads/day，另有 1,000 writes/day、1,000 deletes/day、1,000 list requests/day。
- Relay 默认建议 Worker cron 每 3 分钟运行一次：`*/3 * * * *`。一天是 480 次 scheduled checks，低于 500 次。这个 scheduled check 会执行 KV list；对于每天 1,000 次的 KV list 额度来说，500 次就是 50% 提醒线。保持 3 分钟一次，通常可以避开“用量到 50%”这类提醒邮件。
- 如果你更在意通知延迟，可以改成每 2 分钟一次：`*/2 * * * *`。一天是 720 次，仍低于硬性免费额度，但可能每天收到一封用量提醒邮件。不介意邮件的话可以这么做。

## 选择通知渠道

| 渠道 | 适合 | 取舍 |
|---|---|---|
| Telegram direct | 大多数用户 | 需要 bot token + chat id |
| macOS native | 你在 Mac 前时作为本地 fallback | 机器睡眠时无法通知 |
| Cloudflare relay | 即使笔记本不运行，也希望按时收到延迟通知 | 需要 `wrangler`、Cloudflare 账号和 Worker/KV 设置 |

推荐默认值：Telegram direct + macOS native fallback。如果你需要笔记本不运行时仍能延迟送达，使用 Cloudflare relay。

## 添加一个暂不支持的通知渠道

把这个 prompt 交给你的 AI agent：

```text
给 QuotaMonitor 增加一个名为 <name> 的 notifier。先阅读 docs/adding-notifier.md。
实现一个 Notifier class，包含 name 和 send(Alert) -> None；把它接入
cli/run.py 和 cli/notify_test.py；如果适合，也把它加进 setup wizard；
测试参考 Telegram notifier 的测试方式，补上 pytest contract coverage。
```

## 进阶：Cloudflare relay

当你选择 `cloudflare_relay` 时，向导可以自动部署 relay。手动说明在 `docs/cloudflare.md` 和 `cloudflare-relay/README.md`。

Relay 提供：

- `POST /api/schedule`：把延迟 Telegram 消息存入 KV。
- `scheduled`：cron handler，发送到期 Telegram 消息。默认建议每 3 分钟运行一次（`*/3 * * * *`），一天 480 次。
- 面向 Claude status 风格 payload 的通用 webhook 处理。

## ⚠️ 风险

### Keepalive（自动延续 Claude 5 小时窗口）
- **默认关闭。**
- **ToS 风险**：Anthropic 的 AUP 不鼓励自动化使用。开启前请自己承担风险；如果规模化使用，可能引起注意，甚至影响账号。
- **睡眠限制**：macOS 睡眠时（合盖 / idle sleep），keepalive **不会工作**。`polling` 和 `seamless` 两种策略在睡眠期间都会失效。自然 5 小时 reset 仍会发生，keepalive 救不回来。
- **可选做法**：用台式机 / 常开机器、运行 `caffeinate -i`，或者接受自然 reset。

### Keepalive 内容随机化：能做什么，不能做什么
keepalive 内容会从 10 条短语里随机抽取，同一轮 10 次内不会重复同一句。这只能降低“永远发送同一句 `hi`”这种弱特征。

**它不能规避基于模式的检测**：请求时间、token 量、会话形态、模型选择，都比文本内容更容易形成特征。只要是自动 keep-window-alive，原则上就可能被识别。

### 密钥泄漏
- 不要提交 `.env`。如果 Telegram token 泄漏，通过 @BotFather 轮换。

## 平台支持

| 平台 | 状态 |
|---|---|
| macOS | v1 支持目标 |
| Linux | Best-effort；使用 `docs/linux-systemd.md` |
| Windows | 不支持 |

## 排障

- `config file not found`：运行 `python3.11 -m quota_monitor setup`。
- `Telegram credentials missing`：检查 `~/.quota-monitor/.env`。
- 第二次运行没有通知：如果同一个 reset 已经通知过，这是预期行为。
- State 损坏：QuotaMonitor 会自愈到默认 state，并记录 warning。
- LaunchAgent 没有加载：手动运行 `launchctl load -w ~/Library/LaunchAgents/io.github.frank.quotamonitor.plist` 并检查 stderr。
- Cloudflare 部署失败：运行 `wrangler whoami`、`wrangler tail`，并阅读 `docs/cloudflare.md`。

## 架构

见 `docs/ARCHITECTURE.md`。

核心规则：每次 tick 都通过 Full Replay 从 probe timestamps 推导 quota 窗口。`state.json` 只保存通知去重标记；不保存 window start 或 reset 值。

## 许可证

MIT。见 `LICENSE`。
