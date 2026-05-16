import json
from datetime import datetime, timezone
from quota_monitor.cli.status import show_status


def test_status_prints_no_state_when_missing(capsys, tmp_path):
    rc = show_status(state_path=tmp_path / "no.json", config_path=tmp_path / "no.toml")
    assert rc == 0
    out = capsys.readouterr().out
    assert "No state" in out or "no state" in out.lower()


def test_status_prints_last_alerted_reset(capsys, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {"alerted_for_reset": 1747218000},
        "codex": {"alerted_for_reset": 0, "cooldown_until": 0},
        "keepalive": {"last_seamless_scheduled_for": 0, "phrase_pool_used_indices": [], "phrase_pool_size_at_init": 0},
    }))
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('locale="en"\n[notifiers]\nprimary="telegram"\n')
    rc = show_status(state_path=state_path, config_path=cfg_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "claude" in out.lower()
    assert datetime.fromtimestamp(1747218000, tz=timezone.utc).strftime("%Y-%m-%d") in out
