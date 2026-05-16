from pathlib import Path

from ..platform.schedule import uninstall_launch_agent


def uninstall(*, launch_agent_label: str, plist_path: Path) -> int:
    if plist_path.exists():
        uninstall_launch_agent(plist_path=plist_path)
        print(f"removed LaunchAgent: {plist_path}")
    else:
        print(f"no LaunchAgent at {plist_path} — nothing to do")
    print("NOTE: ~/.quota-monitor/ (config.toml, .env, state.json) was NOT touched.")
    print("      Remove manually if you want a complete wipe.")
    return 0
