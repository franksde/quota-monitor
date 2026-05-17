from pathlib import Path
from quota_monitor.probes.claude import scan_claude

FIXTURES = Path(__file__).parent / "fixtures" / "claude"


def test_scans_app_cache(monkeypatch, tmp_path):
    result = scan_claude(
        app_dir=FIXTURES / "app-cache",
        cli_dir=tmp_path,
        costs_file=tmp_path / "nope.jsonl",
        now=1747200000.0 + 60,   # 1 minute after lastActivityAt
        window_seconds=5 * 3600,
    )
    assert result.source == "claude"
    assert 1747200000.0 in result.timestamps
    assert result.timestamps.count(1747200000.0) == 3   # 3 turns expanded


def test_scans_cli_jsonl_user_messages_only(monkeypatch, tmp_path):
    result = scan_claude(
        app_dir=tmp_path,
        cli_dir=FIXTURES / "cli-jsonl",
        costs_file=tmp_path / "nope.jsonl",
        now=1747312000.0,
        window_seconds=5 * 3600,
    )
    assert len(result.timestamps) == 2   # 2 user messages, assistant skipped


def test_skips_old_files(monkeypatch, tmp_path):
    # Use a very recent `now`; fixtures are from 2026-05 epochs, so they're outside the window.
    result = scan_claude(
        app_dir=FIXTURES / "app-cache",
        cli_dir=FIXTURES / "cli-jsonl",
        costs_file=FIXTURES / "costs.jsonl",
        now=9999999999.0,
        window_seconds=5 * 3600,
    )
    assert result.timestamps == ()


def test_returns_sorted_unique_timestamps(tmp_path):
    result = scan_claude(
        app_dir=FIXTURES / "app-cache",
        cli_dir=FIXTURES / "cli-jsonl",
        costs_file=FIXTURES / "costs.jsonl",
        now=1747400000.0,
        window_seconds=10 * 3600,
    )
    assert list(result.timestamps) == sorted(result.timestamps)


def test_ignores_costs_jsonl(tmp_path):
    """costs.jsonl is not a reliable activity source: for cc-switch / third-party
    users every line is a `model=unknown, tokens=0` placeholder. Even when populated
    it duplicates info already in cli jsonl. The probe must not read it.
    """
    costs = tmp_path / "costs.jsonl"
    # An obviously real-looking timestamp inside the scan window.
    costs.write_text('{"timestamp":"2026-05-15T11:30:00Z","input_tokens":42,"output_tokens":7}\n')
    result = scan_claude(
        app_dir=tmp_path,
        cli_dir=tmp_path,
        costs_file=costs,
        now=1747312000.0,  # ~12:26 on 2026-05-15
        window_seconds=5 * 3600,
    )
    assert result.timestamps == ()
