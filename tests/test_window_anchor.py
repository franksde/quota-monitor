import json
from datetime import datetime

from quota_monitor.core.window import replay_windows, window_from_known_reset


def _epoch(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def test_drift_2026_05_17_known_reset_anchor_beats_scan_window_drift():
    rows = []
    with open("tests/fixtures/claude/drift_2026_05_17_minimal.jsonl", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    timestamps = tuple(_epoch(row["timestamp"]) for row in rows if row["type"] == "user")

    naive = replay_windows(timestamps, correction=0.0)
    anchored = window_from_known_reset(
        timestamps,
        reset_at=_epoch("2026-05-17T05:44:02.457Z"),
    )

    assert naive is not None
    assert naive.reset == _epoch("2026-05-17T06:47:51.634Z")
    assert anchored is not None
    assert anchored.reset == _epoch("2026-05-17T05:44:02.457Z")
    assert anchored.count == 2
