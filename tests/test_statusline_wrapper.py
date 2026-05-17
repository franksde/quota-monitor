import json
from unittest.mock import patch

from quota_monitor.statusline.wrapper import (
    extract_and_cache_rate_limits,
    load_original_command,
    run_wrapper,
)


SAMPLE_STDIN = json.dumps({
    "model": {"id": "claude-opus-4-7"},
    "rate_limits": {
        "five_hour": {"used_percentage": 23.5, "resets_at": 1738425600},
        "seven_day": {"used_percentage": 41.2, "resets_at": 1738857600},
    },
    "context_window": {"used_percentage": 8},
})

SAMPLE_STDIN_NO_LIMITS = json.dumps({
    "model": {"id": "claude-opus-4-7"},
    "context_window": {"used_percentage": 8},
})


def test_extract_writes_cache(tmp_path):
    cache_path = tmp_path / "cache.json"
    extract_and_cache_rate_limits(SAMPLE_STDIN, cache_path)
    assert cache_path.exists()
    data = json.loads(cache_path.read_text())
    assert data["five_hour"]["used_percentage"] == 23.5
    assert data["five_hour"]["resets_at"] == 1738425600
    assert data["seven_day"]["used_percentage"] == 41.2
    assert "captured_at" in data


def test_extract_does_nothing_when_no_rate_limits(tmp_path):
    cache_path = tmp_path / "cache.json"
    extract_and_cache_rate_limits(SAMPLE_STDIN_NO_LIMITS, cache_path)
    assert not cache_path.exists()


def test_extract_does_nothing_on_invalid_json(tmp_path):
    cache_path = tmp_path / "cache.json"
    extract_and_cache_rate_limits("not json {{{", cache_path)
    assert not cache_path.exists()


def test_load_original_command_object_form(tmp_path):
    orig_path = tmp_path / "statusline_original.json"
    orig_path.write_text(json.dumps({
        "original": {
            "type": "command",
            "command": "~/.open-island/bin/oi-statusline",
            "refreshInterval": 5,
        },
    }))
    cmd = load_original_command(orig_path)
    assert cmd == "~/.open-island/bin/oi-statusline"


def test_load_original_command_string_form(tmp_path):
    orig_path = tmp_path / "statusline_original.json"
    orig_path.write_text(json.dumps({"original": "npx ccstatusline@latest"}))
    cmd = load_original_command(orig_path)
    assert cmd == "npx ccstatusline@latest"


def test_load_original_command_null(tmp_path):
    orig_path = tmp_path / "statusline_original.json"
    orig_path.write_text(json.dumps({"original": None}))
    cmd = load_original_command(orig_path)
    assert cmd is None


def test_load_original_command_missing_file(tmp_path):
    cmd = load_original_command(tmp_path / "missing.json")
    assert cmd is None


def test_run_wrapper_without_original(tmp_path, capsys):
    cache_path = tmp_path / "cache.json"
    orig_path = tmp_path / "orig.json"
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = SAMPLE_STDIN
        rc = run_wrapper(cache_path=cache_path, original_path=orig_path)
    assert rc == 0
    assert cache_path.exists()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_run_wrapper_with_original(tmp_path, capsys):
    cache_path = tmp_path / "cache.json"
    orig_path = tmp_path / "orig.json"
    orig_path.write_text(json.dumps({"original": "echo HELLO"}))
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = SAMPLE_STDIN
        rc = run_wrapper(cache_path=cache_path, original_path=orig_path)
    assert rc == 0
    captured = capsys.readouterr()
    assert "HELLO" in captured.out
