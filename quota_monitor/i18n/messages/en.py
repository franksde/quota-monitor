MESSAGES = {
    "alert.title.recovered": "⏳ {source} Quota recovered",
    "alert.body.recovered": "Your {source} 5-hour window has reset at {reset_at_human}. You can resume normal usage.",

    "wizard.welcome": "QuotaMonitor Setup Wizard",
    "wizard.preflight.ok": "Preflight checks passed.",
    "wizard.preflight.fail": "Preflight failed: {missing}. See README §Setup.",
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
