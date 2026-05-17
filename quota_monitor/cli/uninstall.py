from pathlib import Path

from ..i18n import t
from ..platform import paths as platform_paths
from ..platform.schedule import uninstall_launch_agent
from ..statusline.installer import uninstall_wrapper


def uninstall(*, launch_agent_label: str, plist_path: Path) -> int:
    if plist_path.exists():
        uninstall_launch_agent(plist_path=plist_path)
        print(f"removed LaunchAgent: {plist_path}")
    else:
        print(f"no LaunchAgent at {plist_path} — nothing to do")

    settings_path = platform_paths.claude_settings_file()
    backup_path = platform_paths.statusline_original()
    restored_statusline = False
    if backup_path.exists():
        restored_statusline = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
        if restored_statusline:
            print(t("uninstall.statusline.restored"))
            print(t("uninstall.statusline.verify_cmd"))
        else:
            print(t("uninstall.statusline.skipped_manual"))

    cleanup_paths = [
        platform_paths.rate_limits_cache(),
        platform_paths.calibration_file(),
    ]
    if restored_statusline:
        cleanup_paths.append(platform_paths.statusline_original())
    for path in cleanup_paths:
        if path.exists():
            path.unlink()

    print("NOTE: ~/.quota-monitor/ (config.toml, .env, state.json) was NOT touched.")
    print("      Remove manually if you want a complete wipe.")
    return 0
