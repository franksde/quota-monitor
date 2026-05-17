import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape


def _xml_text(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})


def generate_launch_agent_plist(
    *,
    label: str,
    program_arguments: list[str],
    interval_seconds: int,
    stdout_log: Path,
    stderr_log: Path,
) -> str:
    args_xml = "\n".join(f"    <string>{_xml_text(a)}</string>" for a in program_arguments)
    # PATH explicitly includes both Homebrew prefixes (Apple Silicon and
    # Intel) and MacPorts. launchd's default PATH is /usr/bin:/bin:/usr/sbin:/sbin
    # which can't find brew-installed tmux, claude, node, etc. — the cause of
    # the silent keepalive failures users have hit in the wild.
    path_value = "/opt/homebrew/bin:/usr/local/bin:/opt/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{_xml_text(label)}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>{path_value}</string>
  </dict>
  <key>StartInterval</key>
  <integer>{interval_seconds}</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{_xml_text(stdout_log)}</string>
  <key>StandardErrorPath</key>
  <string>{_xml_text(stderr_log)}</string>
</dict>
</plist>
"""


def install_launch_agent(*, plist_path: Path, plist_content: str) -> None:
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    if plist_path.exists():
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            print(f"[warn] launchctl unload returned {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
    plist_path.write_text(plist_content)
    result = subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print(f"[warn] launchctl load returned {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        print("  Try manually: launchctl load -w " + str(plist_path), file=sys.stderr)


def uninstall_launch_agent(*, plist_path: Path) -> None:
    if plist_path.exists():
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            print(f"[warn] launchctl unload returned {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        plist_path.unlink()
