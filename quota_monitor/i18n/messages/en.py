MESSAGES = {
    "alert.title.recovered": "⏳ {source} Quota recovered",
    "alert.body.recovered": "Your {source} 5-hour window has reset at {reset_at_human}. You can resume normal usage.",

    "wizard.welcome": "QuotaMonitor Setup Wizard",
    "wizard.preflight.ok": "Preflight checks passed.",
    "wizard.preflight.fail": "Preflight failed: {missing}. See README §Setup.",
    "wizard.step2.title": "\n=== (2/8) Services to monitor ===",
    "wizard.step2.claude": "Monitor Claude?",
    "wizard.step2.codex": "Monitor Codex (requires ~/.codex/auth.json)?",
    "wizard.step3.title": "\n=== (3/8) Notification ===",
    "wizard.step3.primary": "Primary notifier:",
    "wizard.step3.fallback": "Fallback when primary fails:",
    "wizard.step4.title": "\n=== (4/8) Telegram credentials ===",
    "wizard.step4.use_existing": "Found Telegram credentials in existing .env. Reuse them?",
    "wizard.step4.token": "Bot token",
    "wizard.step4.chat_id": "Chat ID",
    "wizard.step4.test": "Send a test message?",
    "wizard.step5.title": "\n=== (5/8) Cloudflare relay deployment ===",
    "wizard.step5.preflight_fail": "[error] CF preflight failed:",
    "wizard.step5.fix_rerun": "Fix and re-run setup.",
    "wizard.step5.deploy_fail": "[error] Cloudflare deploy failed. Re-run setup once you fix the issue.",
    "wizard.step5.deployed": "Deployed: {url}",
    "wizard.step5.how_to_proceed": "How would you like to proceed?",
    "wizard.step5.worker_check": "\nChecking for existing Worker '{name}'...",
    "wizard.step5.worker_exists": "[!] Worker '{name}' already exists.",
    "wizard.step5.worker_action.options": ["Overwrite existing Worker (Recommended if reinstalling)", "Deploy with a different Worker name", "Abort deployment"],
    "wizard.step5.worker_new_name": "Enter new Worker name (e.g. my-quota-relay)",
    "wizard.step5.queue_create": "\nEnsuring Queue '{name}' exists...",
    "wizard.step5.kv_create": "Provisioning KV namespace '{name}' (for schedule update support)...",
    "wizard.step5.kv_skipped": "[warn] KV provisioning failed; the relay will run but won't be able to supersede outdated scheduled alerts.",
    "wizard.step5.push_secrets": "\nPushing secrets to Cloudflare...",
    "wizard.step5.deploying": "\nDeploying worker...",
    "wizard.step6.title": "\n=== (6/8) Keepalive ===",
    "wizard.step6.enable": "Enable keepalive?",
    "wizard.step7.title": "\n=== (8/8) Schedule install ===",
    "wizard.step7.install": "Install scheduler:",
    "wizard.step7.install.options": ["LaunchAgent (recommended)", "Print crontab line only", "Skip"],
    "wizard.step3.primary.options": ["telegram (direct - fails if Mac sleeps)", "macos_native", "cloudflare_relay (advanced - cloud scheduled, Mac can sleep)"],
    "wizard.step3.fallback.options": ["macos_native", "(none)"],
    "wizard.complete": "Setup complete. First scan in ~5 minutes.",
    "wizard.test_scheduled": "Test message scheduled — it will arrive via Telegram in ~5 seconds.",
    "wizard.keepalive.warning": (
        "ℹ️ Keepalive sends automated requests to Claude Code to keep your 5-hour quota window active.\n"
        "⚠️ Risks & Limitations:\n"
        "  1. ToS — Anthropic AUP may classify automated keepalive as abuse.\n"
        "  2. Sleep — seamless strategy stops working while macOS sleeps.\n"
        "     The natural 5h reset still happens; keepalive cannot save it if the Mac is asleep.\n"
    ),
    "wizard.statusline.title": "\n=== ({step}) StatusLine Precise Usage Tracking ===",
    "wizard.statusline.enable_fresh": (
        "Enable statusLine usage tracking? A lightweight script will read real-time "
        "quota data from Claude Code."
    ),
    "wizard.statusline.enable_existing": (
        "Detected custom status line tool (`{cmd_preview}`). Allow wrapping it to capture "
        "precise quota data? (Your existing tool's display will not be affected)"
    ),
    "wizard.statusline.already_configured": "StatusLine wrapper already configured. Skipping.",
    "wizard.statusline.installed": "✓ StatusLine wrapper installed.",
    "wizard.statusline.precise_threshold": (
        "When precise Claude quota usage is available, alert at what usage percentage?"
    ),

    "cli.status.no_state": "No state yet. Run `quota-monitor run` first.",
    "cli.status.window": "{source} window: starts {start}, resets {reset}",

    "uninstall.statusline.restored": "✓ StatusLine wrapper removed. Original status line restored.",
    "uninstall.statusline.skipped_manual": "StatusLine has been manually changed since install. Skipping restore.",
    "uninstall.statusline.skipped_no_backup": "No statusLine backup found. Skipping restore.",
    "uninstall.statusline.verify_cmd": "  To verify: cat ~/.claude/settings.json | jq .statusLine",

    "alert.suffix.estimated": " (estimated from local conversation logs)",

    "log.probe_failed": "[warn] {source} probe failed: {error}",
    "log.state_corrupted": "[warn] state file corrupted ({error}); resetting to defaults",
    "log.keepalive_fired": "[info] keepalive sent: {phrase}",
    "log.statusline_healed": "[info] statusLine was overwritten externally; wrapper reinstalled",
    "log.statusline_heal_failed": "[warn] statusLine self-heal failed: {error}",
}
