import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _run_wrangler(args: list[str], *, cwd: Path, stdin: Optional[str] = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["wrangler", *args],
            cwd=cwd, input=stdin,
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "wrangler not found in PATH"


def deploy_cf_relay(
    *,
    relay_dir: Path,
    telegram_bot_token: str,
    telegram_chat_id: str,
) -> Optional[str]:
    from ._input import ask_choice, ask_string
    from ..i18n import t

    worker_name = "quota-monitor-relay"
    print(t("wizard.step5.worker_check", name=worker_name))
    rc, out, err = _run_wrangler(["worker", "list"], cwd=relay_dir)
    worker_exists = False
    if rc == 0:
        try:
            import json
            workers = json.loads(out)
            if any(w.get("id") == worker_name for w in workers):
                worker_exists = True
        except Exception:
            if worker_name in out:
                worker_exists = True

    if worker_exists:
        print(t("wizard.step5.worker_exists", name=worker_name))
        idx = ask_choice(
            t("wizard.step5.how_to_proceed"),
            t("wizard.step5.worker_action.options"),
            default=0
        )
        if idx == 1:
            worker_name = ask_string(t("wizard.step5.worker_new_name"))
            if not worker_name:
                return None
        elif idx == 2:
            return None

    # Write wrangler.toml from template
    template = (relay_dir / "wrangler.toml.example").read_text()
    toml = template
    if worker_name != "quota-monitor-relay":
        toml = re.sub(r'name\s*=\s*"[^"]+"', f'name = "{worker_name}"', toml)
    (relay_dir / "wrangler.toml").write_text(toml)

    print(t("wizard.step5.push_secrets"))
    for secret_name, secret_value in [
        ("TELEGRAM_BOT_TOKEN", telegram_bot_token),
        ("TELEGRAM_CHAT_ID", telegram_chat_id),
    ]:
        rc, _, err = _run_wrangler(["secret", "put", secret_name], cwd=relay_dir, stdin=secret_value + "\n")
        if rc != 0:
            print(f"[error] secret put {secret_name} failed: {err}", file=sys.stderr)
            return None

    # Ensure the Queue exists before deploying.
    queue_name = "quota-monitor-alerts"
    print(t("wizard.step5.queue_create", name=queue_name))
    rc, _, err = _run_wrangler(["queues", "create", queue_name], cwd=relay_dir)
    if rc != 0 and "already exists" not in err:
        print(f"[error] wrangler queues create failed: {err}", file=sys.stderr)
        return None

    print(t("wizard.step5.deploying"))
    rc, out, err = _run_wrangler(["deploy"], cwd=relay_dir)
    if rc != 0:
        print(f"[error] wrangler deploy failed: {err}", file=sys.stderr)
        return None
    m = re.search(r"https://[A-Za-z0-9.-]+\.workers\.dev[^\s]*", out)
    if not m:
        print(f"[error] could not parse deploy URL from output:\n{out}", file=sys.stderr)
        return None
    return m.group(0)
