import json
import threading
from dataclasses import replace
from pathlib import Path
import pytest
from quota_monitor.core.state import State, ClaudeState, CodexState, load_state, save_state, default_state


def test_default_state_has_schema_version():
    s = default_state()
    assert s.schema_version == 1
    assert s.claude.alerted_for_reset == 0
    assert s.claude.last_known_good_reset_at == 0
    assert s.claude.keepalive_attempted_for_reset == 0
    assert s.claude.keepalive_attempt_count == 0
    assert s.codex.alerted_for_reset == 0
    assert s.codex.last_fetch_at == 0
    assert s.codex.last_used_percent == 0
    assert s.codex.last_reset_at == 0
    assert s.keepalive.phrase_pool_used_indices == ()


def test_load_old_claude_state_defaults_keepalive_fields(tmp_path):
    """Old state.json without keepalive_attempted_for_reset / _attempt_count
    must load cleanly with zeros, equivalent to first-run."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {
            "alerted_for_reset": 0,
            "cooldown_until": 0,
            "last_known_good_reset_at": 12345.0,
            "scheduled_alert_reset_at": 99999,
        },
        "codex": {},
        "keepalive": {},
    }))

    loaded = load_state(path)

    assert loaded.claude.last_known_good_reset_at == 12345.0
    assert loaded.claude.scheduled_alert_reset_at == 99999
    assert loaded.claude.keepalive_attempted_for_reset == 0
    assert loaded.claude.keepalive_attempt_count == 0


def test_save_then_load_roundtrips_keepalive_fields(tmp_path):
    path = tmp_path / "state.json"
    s = replace(
        default_state(),
        claude=ClaudeState(
            keepalive_attempted_for_reset=1_000_000,
            keepalive_attempt_count=2,
        ),
    )
    save_state(path, s)
    loaded = load_state(path)
    assert loaded.claude.keepalive_attempted_for_reset == 1_000_000
    assert loaded.claude.keepalive_attempt_count == 2


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    s = replace(
        default_state(),
        claude=ClaudeState(alerted_for_reset=1000 + 5 * 3600, last_known_good_reset_at=20_000),
        codex=CodexState(last_fetch_at=1_000, last_used_percent=29, last_reset_at=2_000),
    )
    save_state(path, s)
    loaded = load_state(path)
    assert loaded.claude.alerted_for_reset == 1000 + 5 * 3600
    assert loaded.claude.last_known_good_reset_at == 20_000
    assert loaded.codex.last_fetch_at == 1_000
    assert loaded.codex.last_used_percent == 29
    assert loaded.codex.last_reset_at == 2_000


def test_load_old_codex_state_defaults_fetch_hint_fields(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {"alerted_for_reset": 0, "cooldown_until": 0},
        "codex": {"alerted_for_reset": 123, "cooldown_until": 456},
        "keepalive": {
            "last_seamless_scheduled_for": 0,
            "phrase_pool_used_indices": [],
            "phrase_pool_size_at_init": 0,
        },
    }))

    loaded = load_state(path)

    assert loaded.codex.alerted_for_reset == 123
    assert loaded.codex.cooldown_until == 456
    assert loaded.codex.last_fetch_at == 0
    assert loaded.codex.last_used_percent == 0
    assert loaded.codex.last_reset_at == 0


def test_load_old_claude_state_defaults_known_good_reset(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {"alerted_for_reset": 123, "cooldown_until": 456},
        "codex": {"alerted_for_reset": 0, "cooldown_until": 0},
        "keepalive": {
            "last_seamless_scheduled_for": 0,
            "phrase_pool_used_indices": [],
            "phrase_pool_size_at_init": 0,
        },
    }))

    loaded = load_state(path)

    assert loaded.claude.alerted_for_reset == 123
    assert loaded.claude.cooldown_until == 456
    assert loaded.claude.last_known_good_reset_at == 0


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


def test_concurrent_save_state_serializes_tmp_write(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    barrier = threading.Barrier(2)
    original_write_text = Path.write_text

    def slow_tmp_write(self, *args, **kwargs):
        result = original_write_text(self, *args, **kwargs)
        if self == tmp:
            try:
                barrier.wait(timeout=0.2)
            except threading.BrokenBarrierError:
                pass
        return result

    monkeypatch.setattr(Path, "write_text", slow_tmp_write)
    states = [
        replace(default_state(), claude=ClaudeState(alerted_for_reset=111)),
        replace(default_state(), claude=ClaudeState(alerted_for_reset=222)),
    ]
    errors = []

    def worker(state):
        try:
            save_state(path, state)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(state,)) for state in states]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert load_state(path).claude.alerted_for_reset in {111, 222}
