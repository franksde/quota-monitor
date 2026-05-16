MESSAGES = {
    "alert.title.recovered": "⏳ {source} 额度已恢复",
    "alert.body.recovered": "你的 {source} 5 小时窗口已于 {reset_at_human} 重置,可以继续使用了。",

    "wizard.welcome": "QuotaMonitor 配置向导",
    "wizard.preflight.ok": "前置检查通过。",
    "wizard.preflight.fail": "前置检查失败:{missing}。请参考 README §Setup。",
    "wizard.step2.title": "\n=== (2/7) 监控服务 ===",
    "wizard.step2.claude": "监控 Claude?",
    "wizard.step2.codex": "监控 Codex (需要 ~/.codex/auth.json)?",
    "wizard.step3.title": "\n=== (3/7) 通知配置 ===",
    "wizard.step3.primary": "首选通知渠道:",
    "wizard.step3.fallback": "备用通知渠道(当首选失败时):",
    "wizard.step4.title": "\n=== (4/7) Telegram 凭证 ===",
    "wizard.step4.use_existing": "使用现有 .env 中的 Telegram 凭证。",
    "wizard.step4.token": "Bot token",
    "wizard.step4.chat_id": "Chat ID",
    "wizard.step4.test": "发送测试消息?",
    "wizard.step5.title": "\n=== (5/7) 部署 Cloudflare relay ===",
    "wizard.step5.preflight_fail": "[error] CF 前置检查失败:",
    "wizard.step5.fix_rerun": "请修复后重新运行 setup。",
    "wizard.step5.deploy_fail": "[error] Cloudflare 部署失败。请解决问题后重新运行 setup。",
    "wizard.step5.deployed": "已部署: {url}",
    "wizard.step6.title": "\n=== (6/7) 防休眠 (Keepalive) ===",
    "wizard.step6.enable": "启用防休眠?",
    "wizard.step6.strategy": "策略:",
    "wizard.step7.title": "\n=== (7/7) 定时任务安装 ===",
    "wizard.step7.install": "安装调度器:",
    "wizard.step7.install.options": ["LaunchAgent (推荐)", "仅打印 crontab 配置", "跳过"],
    "wizard.step6.strategy.options": ["polling (默认)", "seamless (高级)"],
    "wizard.step3.primary.options": ["telegram (直连)", "macos_native (本地通知)", "cloudflare_relay (高级)"],
    "wizard.step3.fallback.options": ["macos_native (本地通知)", "(无)"],
    "wizard.complete": "配置完成。约 5 分钟后首次扫描。",
    "wizard.keepalive.warning": (
        "⚠️ Keepalive 风险:\n"
        "  1. ToS — Anthropic AUP 可能将自动 keepalive 归类为滥用。\n"
        "  2. 睡眠 — polling 与 seamless 在 macOS 睡眠期间都会停止工作。\n"
        "     自然 5h 重置仍会发生;keepalive 无法挽救。\n"
    ),

    "cli.status.no_state": "尚无状态。请先运行 `quota-monitor run`。",
    "cli.status.window": "{source} 窗口:起 {start},终 {reset}",

    "log.probe_failed": "[warn] {source} probe failed: {error}",
    "log.state_corrupted": "[warn] 状态文件损坏 ({error});重置为默认",
    "log.keepalive_fired": "[info] keepalive 已发送:{phrase}",
}
