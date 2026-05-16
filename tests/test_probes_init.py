from quota_monitor.probes import ProbeResult


def test_probe_result_carries_source_and_timestamps():
    r = ProbeResult(source="claude", timestamps=(1.0, 2.0, 3.0))
    assert r.source == "claude"
    assert r.timestamps == (1.0, 2.0, 3.0)
    assert r.extra == {}


def test_probe_result_extra_is_dict():
    r = ProbeResult(source="codex", timestamps=(), extra={"reset_at": 999})
    assert r.extra["reset_at"] == 999


def test_probe_result_is_immutable():
    import dataclasses
    r = ProbeResult(source="claude", timestamps=())
    try:
        r.source = "codex"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("ProbeResult should be frozen")
