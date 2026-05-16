import json
from dataclasses import replace
from pathlib import Path
import pytest
from quota_monitor.core.state import State, ClaudeState, load_state, save_state, default_state


def test_default_state_has_schema_version():
    s = default_state()
    assert s.schema_version == 1
    assert s.claude.alerted_for_reset == 0
    assert s.codex.alerted_for_reset == 0
    assert s.keepalive.phrase_pool_used_indices == ()


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    s = replace(default_state(), claude=ClaudeState(alerted_for_reset=1000 + 5 * 3600))
    save_state(path, s)
    loaded = load_state(path)
    assert loaded.claude.alerted_for_reset == 1000 + 5 * 3600


def test_load_missing_file_returns_default(tmp_path):
    s = load_state(tmp_path / "no.json")
    assert s == default_state()


def test_load_corrupted_file_returns_default(tmp_path, capsys):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    s = load_state(path)
    assert s == default_state()
    err = capsys.readouterr().err
    assert "corrupted" in err.lower() or "warn" in err.lower()


def test_atomic_write_no_partial_state(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    save_state(path, default_state())
    original = path.read_text()
    # Simulate failure during write: monkeypatch os.replace to raise after tmp written.
    import quota_monitor.core.state as state_mod

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(state_mod.os, "replace", boom)
    with pytest.raises(OSError):
        s = replace(default_state(), claude=ClaudeState(alerted_for_reset=999))
        save_state(path, s)
    # Original file unchanged.
    assert path.read_text() == original
