> English | [简体中文](#)

[切换语言: [English](README.md) | 中文]

# QuotaMonitor

> 监控 Claude / Codex 的 5 小时 quota 窗口，并在重置时通知你。零运行时依赖 Python，可选 Cloudflare relay。

## Setup with your AI Agent (recommended)

这个工具假设你有本地 AI agent（Claude Code / Codex / Gemini CLI / OpenClaw / Hermes）。最顺滑的安装方式，是先让 agent 帮你把外部依赖准备好，然后再运行向导。

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
如果你把 Cloudflare API token 交给 AI agent，请使用 **scoped token**（仅 Workers + KV），不要使用 Global API Key。用完后建议撤销。

## Quickstart (manual)

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

## What it does

QuotaMonitor 扫描本地 Claude 活动日志和 Codex 使用量元数据，推导当前 quota 窗口，并在重置可用时发送通知。它只保存很小的状态标记，例如“这个 reset 已经通知过”，不会保存对话内容。

可选功能：

- Telegram direct 通知。
- macOS native notification fallback。
- Cloudflare relay，用于笔记本睡眠或关机时的延迟通知。
- Claude keepalive 策略，默认关闭。

## How it works (in 30 seconds)

1. `load_config()` 读取 TOML + `.env`。Schema 校验失败时退出，并给出明确 setup 提示。
2. `load_state()` 读取 `~/.quota-monitor/state.json`。损坏时重置为默认状态并记录 warning。
3. 启用的 probes 收集时间戳或用量元数据。单个 probe 失败只记录 warning，其余继续。
4. `core.window.replay_windows()` 只根据时间戳推导最新 5 小时窗口。State 不参与窗口切分。
5. `decide_alerts()` 只为尚未通知过的 reset point 产生 alert decision。
6. `dispatch_alert()` 带重试发送到 primary notifier，然后 fallback。只有 notifier 成功后才更新 state。
7. 只有显式启用时，才运行可选 keepalive 逻辑。

## Safety & privacy

- 零运行时依赖：仅使用 Python stdlib。
- Local-first：配置、密钥和状态都在 `~/.quota-monitor/`。
- 密钥放在 `.env` 或 Cloudflare Worker secrets，绝不应提交入仓。
- Claude probe 读取本地文件里的元数据和时间戳，不上传对话内容。
- Cloudflare relay 是可选功能。启用后，只会把计划发送的 alert payload 发到你自己的 Worker。

## Cost

- 本地模式成本为 $0。
- Telegram Bot API 对正常个人使用免费。
- Cloudflare relay 使用 Workers + KV。免费层足够典型个人 QuotaMonitor 使用：每 5 分钟一次扫描和少量延迟 alert，远低于 100k requests/day 与 100k KV operations/day。

## Choose your notification channel

| Channel | 适合 | 取舍 |
|---|---|---|
| Telegram direct | 大多数用户 | 需要 bot token + chat id |
| macOS native | 你在 Mac 前时作为本地 fallback | 机器睡眠时无法通知 |
| Cloudflare relay | 即使笔记本不运行，也希望按时收到延迟通知 | 需要 `wrangler`、Cloudflare 账号和 Worker/KV 设置 |

推荐默认值：Telegram direct + macOS native fallback。如果你需要笔记本不运行时仍能延迟送达，使用 Cloudflare relay。

## Adding a channel we don't support

把这个 prompt 交给你的 AI agent：

```text
Add a new QuotaMonitor notifier named <name>. Read docs/adding-notifier.md.
Implement a Notifier class with name and send(Alert) -> None, wire it into
cli/run.py and cli/notify_test.py, add setup wizard options if appropriate,
and add pytest contract coverage following the Telegram notifier tests.
```

## Advanced: Cloudflare relay

当你选择 `cloudflare_relay` 时，向导可以自动部署 relay。手动说明在 `docs/cloudflare.md` 和 `cloudflare-relay/README.md`。

Relay 提供：

- `POST /api/schedule`：把延迟 Telegram 消息存入 KV。
- `scheduled`：cron handler，发送到期 Telegram 消息。
- 面向 Claude status 风格 payload 的通用 webhook 处理。

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

## Platform support

| Platform | 状态 |
|---|---|
| macOS | v1 支持目标 |
| Linux | Best-effort；使用 `docs/linux-systemd.md` |
| Windows | 不支持 |

## Troubleshooting

- `config file not found`：运行 `python3.11 -m quota_monitor setup`。
- Telegram credentials missing：检查 `~/.quota-monitor/.env`。
- 第二次运行没有通知：如果同一个 reset 已经通知过，这是预期行为。
- State 损坏：QuotaMonitor 会自愈到默认 state，并记录 warning。
- LaunchAgent 没有加载：手动运行 `launchctl load -w ~/Library/LaunchAgents/io.github.frank.quotamonitor.plist` 并检查 stderr。
- Cloudflare 部署失败：运行 `wrangler whoami`、`wrangler tail`，并阅读 `docs/cloudflare.md`。

## Architecture

见 `docs/ARCHITECTURE.md`。

核心规则：每次 tick 都通过 Full Replay 从 probe timestamps 推导 quota 窗口。`state.json` 只保存通知去重标记；不保存 window start 或 reset 值。

## License

MIT。见 `LICENSE`。
