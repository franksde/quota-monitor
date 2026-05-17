import glob
import json
import os
from datetime import datetime
from pathlib import Path

from . import ProbeResult


def _iso_to_epoch(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def scan_claude(*, app_dir: Path, cli_dir: Path, costs_file: Path, now: float, window_seconds: int) -> ProbeResult:
    # Scan 2x window so replay_windows can detect the previous window boundary.
    window_start = now - 2 * window_seconds
    out: list[float] = []

    # 1. Mac App session caches.
    for fpath in glob.glob(str(app_dir / "**" / "*.json"), recursive=True):
        try:
            if os.path.getmtime(fpath) < window_start:
                continue
            with open(fpath) as f:
                data = json.load(f)
            last_active = data.get("lastActivityAt", 0) / 1000.0
            if last_active >= window_start:
                turns = data.get("completedTurns", 1)
                out.extend([last_active] * turns)
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue

    # 2. CLI jsonl (user messages only).
    for fpath in glob.glob(str(cli_dir / "**" / "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(fpath) < window_start:
                continue
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("type") != "user":
                        continue
                    if (rec.get("message") or {}).get("role") != "user":
                        continue
                    ts_str = rec.get("timestamp")
                    if not ts_str:
                        continue
                    try:
                        ts = _iso_to_epoch(ts_str)
                    except ValueError:
                        continue
                    if ts >= window_start:
                        out.append(ts)
        except OSError:
            continue

    # 3. costs.jsonl (extra time-source, full scan).
    try:
        if costs_file.exists() and os.path.getmtime(costs_file) >= window_start:
            with open(costs_file, encoding="utf-8") as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = rec.get("timestamp")
                if not ts_str:
                    continue
                try:
                    ts = _iso_to_epoch(ts_str)
                except ValueError:
                    continue
                if ts >= window_start:
                    out.append(ts)
    except OSError:
        pass

    out.sort()
    return ProbeResult(source="claude", timestamps=tuple(out))
