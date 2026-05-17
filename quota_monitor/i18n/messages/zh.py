MESSAGES = {
    "alert.title.recovered": "⏳ {source} 额度已恢复",
    "alert.body.recovered": "你的 {source} 5 小时窗口已于 {reset_at_human} 重置,可以继续使用了。",

    "wizard.welcome": "QuotaMonitor 配置向导",
    "wizard.preflight.ok": "前置检查通过。",
    "wizard.preflight.fail": "前置检查失败:{missing}。请参考 README §Setup。",
    "wizard.step2.title": "\n=== (2/8) 监控服务 ===",
    "wizard.step2.claude": "监控 Claude?",
    "wizard.step2.codex": "监控 Codex (需要 ~/.codex/auth.json)?",
    "wizard.step3.title": "\n=== (3/8) 通知配置 ===",
    "wizard.step3.primary": "首选通知渠道:",
    "wizard.step3.fallback": "备用通知渠道(当首选失败时):",
    "wizard.step4.title": "\n=== (4/8) Telegram 凭证 ===",
    "wizard.step4.use_existing": "检测到现有 .env 中的 Telegram 凭证，是否复用？",
    "wizard.step4.token": "Bot token",
    "wizard.step4.chat_id": "Chat ID",
    "wizard.step4.test": "发送测试消息?",
    "wizard.step5.title": "\n=== (5/8) 部署 Cloudflare relay ===",
    "wizard.step5.preflight_fail": "[error] CF 前置检查失败:",
    "wizard.step5.fix_rerun": "请修复后重新运行 setup。",
    "wizard.step5.deploy_fail": "[error] Cloudflare 部署失败。请解决问题后重新运行 setup。",
    "wizard.step5.deployed": "已部署: {url}",
    "wizard.step5.how_to_proceed": "你想如何继续？",
    "wizard.step5.worker_check": "\n检查是否存在已部署的 Worker '{name}'...",
    "wizard.step5.worker_exists": "[!] Worker '{name}' 已存在。",
    "wizard.step5.worker_action.options": ["覆盖现有 Worker (重新安装或升级时推荐)", "使用不同的 Worker 名称进行部署", "中止部署"],
    "wizard.step5.worker_new_name": "输入新的 Worker 名称 (例如 my-quota-relay)",
    "wizard.step5.queue_create": "\n正在确保 Queue '{name}' 存在...",
    "wizard.step5.push_secrets": "\n正在将凭证推送到 Cloudflare...",
    "wizard.step5.deploying": "\n正在部署 worker...",
    "wizard.step6.title": "\n=== (6/8) 防休眠 (Keepalive) ===",
    "wizard.step6.enable": "启用防休眠?",
    "wizard.step7.title": "\n=== (8/8) 定时任务安装 ===",
    "wizard.step7.install": "安装调度器:",
    "wizard.step7.install.options": ["LaunchAgent (推荐)", "仅打印 crontab 配置", "跳过"],
    "wizard.step3.primary.options": ["telegram (直连 - 电脑休眠时失效)", "macos_native (本地通知)", "cloudflare_relay (高级 - 云端延迟发送，电脑可休眠)"],
    "wizard.step3.fallback.options": ["macos_native (本地通知)", "(无)"],
    "wizard.complete": "配置完成。约 5 分钟后首次扫描。",
    "wizard.test_scheduled": "测试消息已调度 — 约 5 秒后通过 Telegram 送达。",
    "wizard.keepalive.warning": (
        "ℹ️ 防休眠 (Keepalive) 的作用是自动发送请求，为你保活 Claude Code 的 5 小时额度窗口。\n"
        "⚠️ 风险与限制:\n"
        "  1. 服务条款 — Anthropic AUP 可能将自动化请求归类为滥用。\n"
        "  2. 休眠失效 — seamless 策略在 macOS 休眠期间会停止工作。\n"
        "     自然的 5 小时重置仍会发生；如果电脑休眠，keepalive 无法挽救额度。\n"
    ),
    "wizard.statusline.title": "\n=== ({step}) StatusLine 精确用量追踪 ===",
    "wizard.statusline.enable_fresh": (
        "是否启用 StatusLine 精确用量追踪？将配置一个轻量脚本读取 Claude Code 的实时额度信息。"
    ),
    "wizard.statusline.enable_existing": (
        "检测到已安装自定义状态栏工具（`{cmd_preview}`）。是否同意包装一层以获取精确用量信息？"
        "（不会影响现有状态栏工具的显示效果）"
    ),
    "wizard.statusline.already_configured": "StatusLine wrapper 已配置，跳过。",
    "wizard.statusline.installed": "✓ StatusLine wrapper 已安装。",
    "wizard.statusline.precise_threshold": "当可以读取 Claude 精确额度用量时，达到多少百分比触发提醒？",

    "cli.status.no_state": "尚无状态。请先运行 `quota-monitor run`。",
    "cli.status.window": "{source} 窗口:起 {start},终 {reset}",

    "uninstall.statusline.restored": "✓ StatusLine wrapper 已移除，原状态栏配置已恢复。",
    "uninstall.statusline.skipped_manual": "检测到 statusLine 已被手动更改，跳过还原。",
    "uninstall.statusline.skipped_no_backup": "未找到 statusLine 备份，跳过还原。",
    "uninstall.statusline.verify_cmd": "  检查命令: cat ~/.claude/settings.json | jq .statusLine",

    "alert.suffix.estimated": "（根据本地对话记录时间估算）",

    "log.probe_failed": "[warn] {source} probe failed: {error}",
    "log.state_corrupted": "[warn] 状态文件损坏 ({error});重置为默认",
    "log.keepalive_fired": "[info] keepalive 已发送:{phrase}",
}
