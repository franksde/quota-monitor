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


def test_counts_tool_result_wrappers(tmp_path):
    """Claude Code stores every tool_result as `type=user, role=user` with
    `content=[{type:tool_result, ...}]`. These are NOT user-typed input, but
    each one IS an independent API call against Anthropic that consumes quota
    and contributes to the 5h window boundary. The probe must keep them.
    Filtering them out (an earlier attempt) shifted the computed reset by
    ~13 min in the wrong direction.
    """
    cli = tmp_path / "projects" / "x"
    cli.mkdir(parents=True)
    f = cli / "session.jsonl"
    f.write_text(
        '{"type":"user","message":{"role":"user","content":"hello"},"timestamp":"2026-05-15T12:00:00Z"}\n'
        '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"x","content":"ok"}]},"timestamp":"2026-05-15T12:00:05Z"}\n'
    )
    result = scan_claude(
        app_dir=tmp_path / "nope",
        cli_dir=tmp_path,
        costs_file=tmp_path / "nope.jsonl",
        now=1778850000.0,
        window_seconds=5 * 3600,
    )
    assert 1778846400.0 in result.timestamps   # real input
    assert 1778846405.0 in result.timestamps   # tool_result also counts


def test_excludes_local_command_without_assistant_request(tmp_path):
    cli = tmp_path / "projects" / "x"
    cli.mkdir(parents=True)
    f = cli / "session.jsonl"
    f.write_text(
        '{"type":"user","message":{"role":"user","content":"real prompt"},"timestamp":"2026-05-15T12:00:00Z"}\n'
        '{"type":"assistant","message":{"role":"assistant","content":"ok"},"requestId":"req_real","timestamp":"2026-05-15T12:00:03Z"}\n'
        '{"type":"user","message":{"role":"user","content":"<local-command-caveat>generated locally</local-command-caveat>"},"timestamp":"2026-05-15T12:10:00Z"}\n'
        '{"type":"user","message":{"role":"user","content":"<command-name>/usage</command-name> <command-message>usage</command-message>"},"timestamp":"2026-05-15T12:10:00Z"}\n'
        '{"type":"system","content":"<local-command-stdout>You are currently using your subscription</local-command-stdout>","timestamp":"2026-05-15T12:10:00Z"}\n'
    )
    result = scan_claude(
        app_dir=tmp_path / "nope",
        cli_dir=tmp_path,
        costs_file=tmp_path / "nope.jsonl",
        now=1778850000.0,
        window_seconds=5 * 3600,
    )
    assert result.timestamps == (1778846400.0,)


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
