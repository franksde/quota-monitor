import json
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
    """Half-automatic CF deploy. Returns the deployed worker URL on success, None on failure."""
    print("Creating KV namespace ALERTS_KV...")
    rc, out, err = _run_wrangler(["kv", "namespace", "create", "ALERTS_KV"], cwd=relay_dir)
    if rc != 0:
        print(f"[error] kv namespace create failed: {err}", file=sys.stderr)
        return None
    # Wrangler prints either JSON or a human line containing `id = "..."`. Try both.
    kv_id = None
    try:
        kv_id = json.loads(out).get("id")
    except json.JSONDecodeError:
        m = re.search(r'id\s*=\s*"([^"]+)"', out)
        if m:
            kv_id = m.group(1)
    if not kv_id:
        print(f"[error] could not parse KV id from wrangler output:\n{out}", file=sys.stderr)
        return None

    print(f"  KV id = {kv_id}")
    template = (relay_dir / "wrangler.toml.example").read_text()
    toml = template.replace("REPLACE_ME", kv_id)
    (relay_dir / "wrangler.toml").write_text(toml)

    print("Pushing secrets to Cloudflare...")
    for secret_name, secret_value in [
        ("TELEGRAM_BOT_TOKEN", telegram_bot_token),
        ("TELEGRAM_CHAT_ID", telegram_chat_id),
    ]:
        rc, _, err = _run_wrangler(["secret", "put", secret_name], cwd=relay_dir, stdin=secret_value + "\n")
        if rc != 0:
            print(f"[error] secret put {secret_name} failed: {err}", file=sys.stderr)
            return None

    print("Deploying worker...")
    rc, out, err = _run_wrangler(["deploy"], cwd=relay_dir)
    if rc != 0:
        print(f"[error] wrangler deploy failed: {err}", file=sys.stderr)
        return None
    m = re.search(r"https://[A-Za-z0-9.-]+\.workers\.dev[^\s]*", out)
    if not m:
        print(f"[error] could not parse deploy URL from output:\n{out}", file=sys.stderr)
        return None
    return m.group(0)
