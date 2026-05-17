import json

from quota_monitor.statusline.installer import (
    detect_existing_statusline,
    install_wrapper,
    uninstall_wrapper,
    is_our_wrapper,
    StatusLineState,
)


def _write_settings(tmp_path, settings_data):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(settings_data))
    return path


def test_detect_no_statusline(tmp_path):
    settings_path = _write_settings(tmp_path, {"permissions": {}})
    result = detect_existing_statusline(settings_path)
    assert result == StatusLineState.NONE


def test_detect_our_wrapper(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"},
    })
    result = detect_existing_statusline(settings_path)
    assert result == StatusLineState.OUR_WRAPPER


def test_detect_third_party_object(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "~/.open-island/bin/oi-statusline"},
    })
    result = detect_existing_statusline(settings_path)
    assert result == StatusLineState.THIRD_PARTY


def test_detect_third_party_string(tmp_path):
    settings_path = _write_settings(tmp_path, {"statusLine": "npx ccstatusline@latest"})
    result = detect_existing_statusline(settings_path)
    assert result == StatusLineState.THIRD_PARTY


def test_is_our_wrapper():
    assert is_our_wrapper({"type": "command", "command": "python3 -m quota_monitor.statusline"})
    assert is_our_wrapper("python3 -m quota_monitor.statusline --foo")
    assert not is_our_wrapper("~/.open-island/bin/oi-statusline")
    assert not is_our_wrapper({"type": "command", "command": "node /path/to/hud.js"})
    assert not is_our_wrapper(None)


def test_install_wrapper_fresh(tmp_path):
    settings_path = _write_settings(tmp_path, {"permissions": {}})
    backup_path = tmp_path / "statusline_original.json"

    install_wrapper(settings_path=settings_path, backup_path=backup_path)

    settings = json.loads(settings_path.read_text())
    assert "quota_monitor.statusline" in settings["statusLine"]["command"]
    backup = json.loads(backup_path.read_text())
    assert backup["original"] is None


def test_install_wrapper_wraps_existing(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "~/.open-island/bin/oi", "padding": 2},
    })
    backup_path = tmp_path / "statusline_original.json"

    install_wrapper(settings_path=settings_path, backup_path=backup_path)

    settings = json.loads(settings_path.read_text())
    assert "quota_monitor.statusline" in settings["statusLine"]["command"]
    assert settings["statusLine"]["padding"] == 2
    backup = json.loads(backup_path.read_text())
    assert backup["original"]["command"] == "~/.open-island/bin/oi"


def test_uninstall_wrapper_restores(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"},
        "permissions": {"allow": []},
    })
    backup_path = tmp_path / "statusline_original.json"
    backup_path.write_text(json.dumps({
        "original": {"type": "command", "command": "~/.open-island/bin/oi", "padding": 2},
    }))

    restored = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
    assert restored is True

    settings = json.loads(settings_path.read_text())
    assert settings["statusLine"]["command"] == "~/.open-island/bin/oi"
    assert settings["permissions"] == {"allow": []}


def test_uninstall_wrapper_removes_key_if_original_null(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"},
        "permissions": {"allow": []},
    })
    backup_path = tmp_path / "statusline_original.json"
    backup_path.write_text(json.dumps({"original": None}))

    restored = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
    assert restored is True

    settings = json.loads(settings_path.read_text())
    assert "statusLine" not in settings


def test_uninstall_skips_if_not_our_wrapper(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "node /custom/hud.js"},
    })
    backup_path = tmp_path / "statusline_original.json"
    backup_path.write_text(json.dumps({"original": "old_thing"}))

    restored = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
    assert restored is False

    settings = json.loads(settings_path.read_text())
    assert settings["statusLine"]["command"] == "node /custom/hud.js"


def test_uninstall_skips_if_no_backup(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"},
    })
    backup_path = tmp_path / "missing_backup.json"

    restored = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
    assert restored is False
