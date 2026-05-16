MESSAGES = {
    "alert.title.recovered": "⏳ {source} 额度已恢复",
    "alert.body.recovered": "你的 {source} 5 小时窗口已于 {reset_at_human} 重置,可以继续使用了。",

    "wizard.welcome": "QuotaMonitor 配置向导",
    "wizard.preflight.ok": "前置检查通过。",
    "wizard.preflight.fail": "前置检查失败:{missing}。请参考 README §Setup。",
    "wizard.complete": "配置完成。约 5 分钟后首次扫描。",
    "wizard.keepalive.warning": (
        "⚠️ Keepalive 风险:\n"
        "  1. ToS — Anthropic AUP 可能将自动 keepalive 归类为滥用。\n"
        "  2. 睡眠 — polling 与 seamless 在 macOS 睡眠期间都会停止工作。\n"
        "     自然 5h 重置仍会发生;keepalive 无法挽救。\n"
    ),

    "cli.status.no_state": "尚无状态。请先运行 `quota-monitor run`。",
    "cli.status.window": "{source} 窗口:起 {start},终 {reset}",

    "log.probe_failed": "[warn] {source} probe 失败:{error}",
    "log.state_corrupted": "[warn] 状态文件损坏 ({error});重置为默认",
    "log.keepalive_fired": "[info] keepalive 已发送:{phrase}",
}
