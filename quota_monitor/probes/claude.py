import glob
import json
import os
from datetime import datetime
from pathlib import Path

from . import ProbeResult

LOCAL_COMMAND_MARKERS = (
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-caveat>",
    "<local-command-stdout>",
)


def _iso_to_epoch(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def _contains_local_command_marker(value) -> bool:
    if isinstance(value, str):
        return any(marker in value for marker in LOCAL_COMMAND_MARKERS)
    if isinstance(value, list):
        return any(_contains_local_command_marker(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_local_command_marker(item) for item in value.values())
    return False


def _contains_tool_result(value) -> bool:
    if isinstance(value, list):
        return any(isinstance(item, dict) and item.get("type") == "tool_result" for item in value)
    return False


def _has_following_assistant_request(records: list[dict], index: int) -> bool:
    for rec in records[index + 1:]:
        if rec.get("type") == "assistant":
            return bool(rec.get("requestId"))
        if rec.get("type") == "user":
            return False
    return False


def _is_uncounted_local_command(records: list[dict], index: int) -> bool:
    message = records[index].get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    if _contains_tool_result(content):
        return False
    return _contains_local_command_marker(content) and not _has_following_assistant_request(records, index)


def scan_claude(*, app_dir: Path, cli_dir: Path, costs_file: Path, now: float, window_seconds: int) -> ProbeResult:
    # costs_file is accepted for signature compatibility but intentionally unused.
    # It only contains `model=unknown, tokens=0` placeholders for cc-switch /
    # third-party users (100% of entries in observed installs), which polluted
    # replay_windows with phantom activity and shifted reset times by up to 30 min.
    del costs_file

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
            records = []
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            for index, rec in enumerate(records):
                if rec.get("type") != "user":
                    continue
                if (rec.get("message") or {}).get("role") != "user":
                    continue
                if _is_uncounted_local_command(records, index):
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

    out.sort()
    return ProbeResult(source="claude", timestamps=tuple(out))
