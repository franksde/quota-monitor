MESSAGES = {
    "alert.title.recovered": "⏳ {source} Quota recovered",
    "alert.body.recovered": "Your {source} 5-hour window has reset at {reset_at_human}. You can resume normal usage.",

    "wizard.welcome": "QuotaMonitor Setup Wizard",
    "wizard.preflight.ok": "Preflight checks passed.",
    "wizard.preflight.fail": "Preflight failed: {missing}. See README §Setup.",
    "wizard.step2.title": "\n=== (2/7) Services to monitor ===",
    "wizard.step2.claude": "Monitor Claude?",
    "wizard.step2.codex": "Monitor Codex (requires ~/.codex/auth.json)?",
    "wizard.step3.title": "\n=== (3/7) Notification ===",
    "wizard.step3.primary": "Primary notifier:",
    "wizard.step3.fallback": "Fallback when primary fails:",
    "wizard.step4.title": "\n=== (4/7) Telegram credentials ===",
    "wizard.step4.use_existing": "Using Telegram credentials from existing .env.",
    "wizard.step4.token": "Bot token",
    "wizard.step4.chat_id": "Chat ID",
    "wizard.step4.test": "Send a test message?",
    "wizard.step5.title": "\n=== (5/7) Cloudflare relay deployment ===",
    "wizard.step5.preflight_fail": "[error] CF preflight failed:",
    "wizard.step5.fix_rerun": "Fix and re-run setup.",
    "wizard.step5.deploy_fail": "[error] Cloudflare deploy failed. Re-run setup once you fix the issue.",
    "wizard.step5.deployed": "Deployed: {url}",
    "wizard.step6.title": "\n=== (6/7) Keepalive ===",
    "wizard.step6.enable": "Enable keepalive?",
    "wizard.step6.strategy": "Strategy:",
    "wizard.step7.title": "\n=== (7/7) Schedule install ===",
    "wizard.step7.install": "Install scheduler:",
    "wizard.step7.install.options": ["LaunchAgent (recommended)", "Print crontab line only", "Skip"],
    "wizard.step6.strategy.options": ["polling (default)", "seamless (advanced)"],
    "wizard.step3.primary.options": ["telegram (direct)", "macos_native", "cloudflare_relay (advanced)"],
    "wizard.step3.fallback.options": ["macos_native", "(none)"],
    "wizard.complete": "Setup complete. First scan in ~5 minutes.",
    "wizard.keepalive.warning": (
        "⚠️ Keepalive risks:\n"
        "  1. ToS — Anthropic AUP may classify automated keepalive as abuse.\n"
        "  2. Sleep — both polling and seamless strategies stop working while macOS sleeps.\n"
        "     The natural 5h reset still happens; keepalive cannot save it.\n"
    ),

    "cli.status.no_state": "No state yet. Run `quota-monitor run` first.",
    "cli.status.window": "{source} window: starts {start}, resets {reset}",

    "log.probe_failed": "[warn] {source} probe failed: {error}",
    "log.state_corrupted": "[warn] state file corrupted ({error}); resetting to defaults",
    "log.keepalive_fired": "[info] keepalive sent: {phrase}",
}
