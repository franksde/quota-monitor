import json
import re
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Optional


# Wrangler 4.x prefixes stdout with a version banner ("⛅️ wrangler 4.x.x" + a
# rule line) before the actual command output. JSON parsers will choke on this,
# so all helpers below tolerate leading non-JSON garbage by anchoring on the
# first '[' or '{'.

def _strip_to_json(text: str) -> str:
    matches = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not matches:
        return text
    return text[min(matches):]


def _extract_kv_id(text: str) -> Optional[str]:
    """Extract the KV namespace id from a `wrangler kv namespace create`
    success output. Wrangler has emitted at least two formats across versions:

      TOML config snippet: `id = "abc..."`
      JSON config snippet: `"id": "abc..."`

    Both wrappers are handled. KV ids are 32-char lowercase hex.
    """
    m = re.search(r'"id"\s*:\s*"([0-9a-f]{16,})"', text)
    if m:
        return m.group(1)
    m = re.search(r'\bid\s*=\s*"([0-9a-f]{16,})"', text)
    if m:
        return m.group(1)
    return None


def _find_kv_id_in_list(list_out: str, target_name: str) -> Optional[str]:
    """Locate the id for `target_name` in `wrangler kv namespace list` JSON
    output. Banner-tolerant."""
    payload = _strip_to_json(list_out)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"[warn] could not parse KV namespace list output: {e}", file=sys.stderr)
        return None
    if not isinstance(data, list):
        return None
    for ns in data:
        if not isinstance(ns, dict):
            continue
        if ns.get("title", "").endswith(target_name):
            return ns.get("id")
    return None


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


def prepare_cf_relay_workdir(work_dir: Optional[Path] = None) -> Path:
    """Copy bundled Cloudflare relay assets into a writable work directory."""
    work_dir = work_dir or (Path.home() / ".quota-monitor" / "cloudflare-relay")
    bundled = resources.files("quota_monitor.cloudflare_relay")
    for rel in (
        "wrangler.toml.example",
        "package.json",
        "README.md",
        "src/worker.js",
    ):
        src = bundled.joinpath(*rel.split("/"))
        dest = work_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
    return work_dir


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
    if rc != 0 and "already" not in err.lower():
        print(f"[error] wrangler queues create failed: {err}", file=sys.stderr)
        return None

    # Provision the schedule-tombstone KV namespace and wire it into
    # wrangler.toml. Lets quota-monitor implicitly supersede an already-
    # queued delayed alert when the predicted reset time gets refined.
    # Failure here is non-fatal: the worker degrades to no-dedupe behaviour.
    kv_ns_name = "SCHEDULE_TOMBSTONE"
    print(t("wizard.step5.kv_create", name=kv_ns_name))
    rc, out, err = _run_wrangler(["kv", "namespace", "create", kv_ns_name], cwd=relay_dir)
    kv_id = None
    if rc == 0:
        kv_id = _extract_kv_id(out)
    elif "already" in err.lower() or "already" in out.lower():
        # Find the existing namespace id via `wrangler kv namespace list`.
        rc2, list_out, list_err = _run_wrangler(["kv", "namespace", "list"], cwd=relay_dir)
        if rc2 == 0:
            kv_id = _find_kv_id_in_list(list_out, kv_ns_name)
            if kv_id is None:
                print(
                    f"[warn] could not locate KV namespace {kv_ns_name!r} in "
                    f"`wrangler kv namespace list` output",
                    file=sys.stderr,
                )
        else:
            print(f"[warn] `wrangler kv namespace list` failed: {list_err}", file=sys.stderr)
    if kv_id:
        toml_path = relay_dir / "wrangler.toml"
        current = toml_path.read_text()
        kv_block = (
            f'\n[[kv_namespaces]]\nbinding = "{kv_ns_name}"\nid = "{kv_id}"\n'
        )
        if f'binding = "{kv_ns_name}"' not in current:
            toml_path.write_text(current.rstrip() + "\n" + kv_block)
    else:
        print(t("wizard.step5.kv_skipped"), file=sys.stderr)

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
