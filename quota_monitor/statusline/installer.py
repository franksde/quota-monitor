import enum
import json
import os
from pathlib import Path

WRAPPER_MARKER = "quota_monitor.statusline"


class StatusLineState(enum.Enum):
    NONE = "none"
    OUR_WRAPPER = "our_wrapper"
    THIRD_PARTY = "third_party"


def is_our_wrapper(statusline_value) -> bool:
    if statusline_value is None:
        return False
    if isinstance(statusline_value, str):
        return WRAPPER_MARKER in statusline_value
    if isinstance(statusline_value, dict):
        command = statusline_value.get("command", "")
        return WRAPPER_MARKER in (command or "")
    return False


def detect_existing_statusline(settings_path: Path) -> StatusLineState:
    if not settings_path.exists():
        return StatusLineState.NONE
    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return StatusLineState.NONE

    statusline = settings.get("statusLine")
    if statusline is None:
        return StatusLineState.NONE
    if is_our_wrapper(statusline):
        return StatusLineState.OUR_WRAPPER
    return StatusLineState.THIRD_PARTY


def _atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)


def install_wrapper(*, settings_path: Path, backup_path: Path) -> None:
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            settings = {}

    original_statusline = settings.get("statusLine")
    _atomic_write_json(backup_path, {"original": original_statusline})

    new_statusline = {
        "type": "command",
        "command": "python3 -m quota_monitor.statusline",
        "refreshInterval": 5,
    }
    if isinstance(original_statusline, dict):
        for key in ("padding", "hideVimModeIndicator", "refreshInterval"):
            if key in original_statusline:
                new_statusline[key] = original_statusline[key]

    settings["statusLine"] = new_statusline
    _atomic_write_json(settings_path, settings)


def uninstall_wrapper(*, settings_path: Path, backup_path: Path) -> bool:
    if not backup_path.exists() or not settings_path.exists():
        return False

    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    if not is_our_wrapper(settings.get("statusLine")):
        return False

    try:
        backup = json.loads(backup_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    original = backup.get("original")
    if original is None:
        settings.pop("statusLine", None)
    else:
        settings["statusLine"] = original

    _atomic_write_json(settings_path, settings)
    return True
