# StatusLine Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add precise 5h/7d quota tracking via Claude Code statusLine integration, with EMA-based dynamic calibration and graceful fallback to local file replay estimation.

**Architecture:** A Python one-shot statusLine wrapper intercepts Claude Code's stdin JSON, caches `rate_limits` locally, and forwards to the original statusLine command. The existing `run_once` pipeline reads this cache for precise values, falling back to `replay_windows` estimation when cache expires. A calibration module collects drift samples and adjusts the correction constant via EMA.

**Tech Stack:** Python 3.10+ stdlib only (json, subprocess, os, sys, time, dataclasses). No new external dependencies.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `quota_monitor/platform/paths.py` | New path helpers for cache/calibration/settings files |
| `quota_monitor/core/calibration.py` | EMA algorithm, calibration.json read/write, drift sampling |
| `quota_monitor/core/window.py` | Add optional `correction` parameter, change default to -360 |
| `quota_monitor/probes/precise.py` | Read rate_limits_cache.json, return PreciseUsage or None |
| `quota_monitor/statusline/__init__.py` | Empty package marker |
| `quota_monitor/statusline/__main__.py` | Entry point for `python -m quota_monitor.statusline` |
| `quota_monitor/statusline/wrapper.py` | Core: read stdin → write cache → exec original → pipe stdout |
| `quota_monitor/statusline/installer.py` | Install/uninstall statusLine config in settings.json |
| `quota_monitor/i18n/messages/en.py` | New keys: `wizard.statusline.*`, `uninstall.statusline.*`, `alert.suffix.*` |
| `quota_monitor/i18n/messages/zh.py` | Same keys in Chinese |
| `quota_monitor/cli/run.py` | Integrate precise/estimated decision + calibration sampling |
| `quota_monitor/cli/setup.py` | New wizard step for statusLine |
| `quota_monitor/cli/uninstall.py` | Safe statusLine restore |
| `tests/test_calibration.py` | EMA, outlier filtering, sample truncation |
| `tests/test_precise_probe.py` | Cache reading, expiry logic |
| `tests/test_statusline_wrapper.py` | Wrapper stdin/stdout piping |
| `tests/test_statusline_installer.py` | Install/uninstall/conflict detection |

---

### Task 1: Platform Paths

**Files:**
- Modify: `quota_monitor/platform/paths.py`
- Test: `tests/test_platform_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_platform_paths.py — append to existing file

from quota_monitor.platform import paths


def test_rate_limits_cache():
    p = paths.rate_limits_cache()
    assert str(p).endswith(".quota-monitor/rate_limits_cache.json")


def test_calibration_file():
    p = paths.calibration_file()
    assert str(p).endswith(".quota-monitor/calibration.json")


def test_statusline_original():
    p = paths.statusline_original()
    assert str(p).endswith(".quota-monitor/statusline_original.json")


def test_claude_settings_file():
    p = paths.claude_settings_file()
    assert str(p).endswith(".claude/settings.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_platform_paths.py::test_rate_limits_cache tests/test_platform_paths.py::test_calibration_file tests/test_platform_paths.py::test_statusline_original tests/test_platform_paths.py::test_claude_settings_file -v`
Expected: FAIL with `AttributeError: module 'quota_monitor.platform.paths' has no attribute 'rate_limits_cache'`

- [ ] **Step 3: Write minimal implementation**

Add to `quota_monitor/platform/paths.py`:

```python
def rate_limits_cache() -> Path:
    return user_data_dir() / "rate_limits_cache.json"


def calibration_file() -> Path:
    return user_data_dir() / "calibration.json"


def statusline_original() -> Path:
    return user_data_dir() / "statusline_original.json"


def claude_settings_file() -> Path:
    return Path.home() / ".claude" / "settings.json"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_platform_paths.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/platform/paths.py tests/test_platform_paths.py
git commit -m "feat(paths): add rate_limits_cache, calibration, statusline paths"
```

---

### Task 2: Core Calibration Module

**Files:**
- Create: `quota_monitor/core/calibration.py`
- Create: `tests/test_calibration.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_calibration.py
import json
from pathlib import Path

from quota_monitor.core.calibration import (
    CalibrationState,
    Sample,
    load_calibration,
    save_calibration,
    compute_correction,
    record_sample,
    DEFAULT_CORRECTION_SECONDS,
    EMA_ALPHA,
    MAX_SAMPLES,
    OUTLIER_THRESHOLD_SECONDS,
)


def test_default_correction_is_negative_360():
    assert DEFAULT_CORRECTION_SECONDS == -360


def test_load_missing_file_returns_defaults(tmp_path):
    state = load_calibration(tmp_path / "missing.json")
    assert state.current_correction_seconds == DEFAULT_CORRECTION_SECONDS
    assert state.samples == []


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "cal.json"
    state = CalibrationState(
        current_correction_seconds=-340.0,
        samples=[Sample(ts=1000, precise_reset=2000, computed_reset=2350, drift=-350)],
    )
    save_calibration(path, state)
    loaded = load_calibration(path)
    assert loaded.current_correction_seconds == -340.0
    assert len(loaded.samples) == 1
    assert loaded.samples[0].drift == -350


def test_compute_correction_returns_default_when_few_samples():
    samples = [Sample(ts=1, precise_reset=2, computed_reset=3, drift=-1)]
    assert compute_correction(samples) == DEFAULT_CORRECTION_SECONDS


def test_compute_correction_with_enough_samples():
    samples = [
        Sample(ts=i, precise_reset=1000+i, computed_reset=1000+i+360, drift=-360)
        for i in range(5)
    ]
    result = compute_correction(samples)
    assert abs(result - (-360)) < 1  # all drifts are -360, EMA converges to -360


def test_compute_correction_weights_recent_samples_more():
    samples = [
        Sample(ts=1, precise_reset=100, computed_reset=460, drift=-360),
        Sample(ts=2, precise_reset=200, computed_reset=560, drift=-360),
        Sample(ts=3, precise_reset=300, computed_reset=660, drift=-360),
        Sample(ts=4, precise_reset=400, computed_reset=700, drift=-300),
        Sample(ts=5, precise_reset=500, computed_reset=800, drift=-300),
    ]
    result = compute_correction(samples)
    # Recent drifts are -300, so EMA should be closer to -300 than -360
    assert result > -360
    assert result < -300


def test_compute_correction_excludes_outliers():
    samples = [
        Sample(ts=1, precise_reset=100, computed_reset=460, drift=-360),
        Sample(ts=2, precise_reset=200, computed_reset=560, drift=-360),
        Sample(ts=3, precise_reset=300, computed_reset=660, drift=-360),
        Sample(ts=4, precise_reset=400, computed_reset=2400, drift=-2000),  # outlier
    ]
    result = compute_correction(samples)
    # Outlier excluded, result should be close to -360
    assert abs(result - (-360)) < 1


def test_record_sample_adds_and_truncates():
    state = CalibrationState(
        current_correction_seconds=-360.0,
        samples=[Sample(ts=i, precise_reset=i+1000, computed_reset=i+1360, drift=-360) for i in range(20)],
    )
    new_state = record_sample(state, precise_reset=99999, computed_reset=100359, ts=21)
    assert len(new_state.samples) == 20  # still max 20
    assert new_state.samples[-1].ts == 21  # newest added
    assert new_state.samples[0].ts == 1  # oldest trimmed (was ts=0)


def test_record_sample_recomputes_correction():
    state = CalibrationState(
        current_correction_seconds=-360.0,
        samples=[Sample(ts=i, precise_reset=i+1000, computed_reset=i+1360, drift=-360) for i in range(5)],
    )
    # Add a sample with drift=-300
    new_state = record_sample(state, precise_reset=6000, computed_reset=6300, ts=6)
    # Correction should shift toward -300
    assert new_state.current_correction_seconds > -360
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_calibration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quota_monitor.core.calibration'`

- [ ] **Step 3: Write implementation**

```python
# quota_monitor/core/calibration.py
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

DEFAULT_CORRECTION_SECONDS = -360
EMA_ALPHA = 0.3
MAX_SAMPLES = 20
OUTLIER_THRESHOLD_SECONDS = 1800


@dataclass
class Sample:
    ts: float
    precise_reset: float
    computed_reset: float
    drift: float


@dataclass
class CalibrationState:
    current_correction_seconds: float = DEFAULT_CORRECTION_SECONDS
    samples: list[Sample] = None

    def __post_init__(self):
        if self.samples is None:
            self.samples = []


def load_calibration(path: Path) -> CalibrationState:
    if not path.exists():
        return CalibrationState()
    try:
        raw = json.loads(path.read_text())
        samples = [Sample(**s) for s in raw.get("samples", [])]
        return CalibrationState(
            current_correction_seconds=raw.get("current_correction_seconds", DEFAULT_CORRECTION_SECONDS),
            samples=samples,
        )
    except (json.JSONDecodeError, OSError, TypeError, KeyError):
        return CalibrationState()


def save_calibration(path: Path, state: CalibrationState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "default_correction_seconds": DEFAULT_CORRECTION_SECONDS,
        "current_correction_seconds": state.current_correction_seconds,
        "ema_alpha": EMA_ALPHA,
        "samples": [asdict(s) for s in state.samples],
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)


def compute_correction(samples: list[Sample]) -> float:
    valid = [s for s in samples if abs(s.drift) <= OUTLIER_THRESHOLD_SECONDS]
    if len(valid) < 3:
        return DEFAULT_CORRECTION_SECONDS
    ema = valid[0].drift
    for s in valid[1:]:
        ema = EMA_ALPHA * s.drift + (1 - EMA_ALPHA) * ema
    return ema


def record_sample(
    state: CalibrationState,
    *,
    precise_reset: float,
    computed_reset: float,
    ts: float,
) -> CalibrationState:
    drift = precise_reset - computed_reset
    sample = Sample(ts=ts, precise_reset=precise_reset, computed_reset=computed_reset, drift=drift)
    new_samples = state.samples + [sample]
    if len(new_samples) > MAX_SAMPLES:
        new_samples = new_samples[-MAX_SAMPLES:]
    new_correction = compute_correction(new_samples)
    return CalibrationState(current_correction_seconds=new_correction, samples=new_samples)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_calibration.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/core/calibration.py tests/test_calibration.py
git commit -m "feat(calibration): EMA-based dynamic correction with outlier filtering"
```

---

### Task 3: Modify window.py for Correction Parameter

**Files:**
- Modify: `quota_monitor/core/window.py`
- Modify: `tests/test_window.py`

- [ ] **Step 1: Write new failing tests**

Append to `tests/test_window.py`:

```python
from quota_monitor.core.window import RESET_CORRECTION_SECONDS


def test_default_correction_is_negative_360():
    assert RESET_CORRECTION_SECONDS == -360


def test_replay_windows_applies_default_correction():
    w = replay_windows((1000.0,))
    assert w.reset == 1000.0 + WINDOW_SECONDS + RESET_CORRECTION_SECONDS


def test_replay_windows_applies_custom_correction():
    w = replay_windows((1000.0,), correction=-120.0)
    assert w.reset == 1000.0 + WINDOW_SECONDS - 120.0


def test_replay_windows_correction_zero():
    w = replay_windows((1000.0,), correction=0.0)
    assert w.reset == 1000.0 + WINDOW_SECONDS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_window.py::test_default_correction_is_negative_360 tests/test_window.py::test_replay_windows_applies_default_correction tests/test_window.py::test_replay_windows_applies_custom_correction tests/test_window.py::test_replay_windows_correction_zero -v`
Expected: FAIL (no RESET_CORRECTION_SECONDS export, no `correction` parameter)

- [ ] **Step 3: Modify window.py**

Replace `quota_monitor/core/window.py`:

```python
from dataclasses import dataclass
from typing import Optional

from .state import State
from ..probes import ProbeResult

WINDOW_SECONDS = 5 * 3600
RESET_CORRECTION_SECONDS = -360


@dataclass(frozen=True)
class LatestWindow:
    start: float
    reset: float
    count: int


@dataclass(frozen=True)
class AlertDecision:
    source: str       # "claude" | "codex"
    reset_at: int     # epoch seconds


def replay_windows(
    timestamps: tuple[float, ...],
    correction: Optional[float] = None,
) -> Optional[LatestWindow]:
    """Full Replay: scan all timestamps left-to-right, opening a new 5h window
    every time `ts >= current_reset`. Returns the LATEST window after replay,
    or None if there are no timestamps.

    The correction parameter adjusts the computed reset time to account for
    consistent drift between local log timestamps and the actual server window.
    """
    if not timestamps:
        return None
    actual_correction = correction if correction is not None else RESET_CORRECTION_SECONDS
    sorted_ts = sorted(timestamps)
    start = sorted_ts[0]
    reset = start + WINDOW_SECONDS
    count = 1
    for ts in sorted_ts[1:]:
        if ts >= reset:
            start = ts
            reset = ts + WINDOW_SECONDS
            count = 1
        else:
            count += 1
    return LatestWindow(start=start, reset=reset + actual_correction, count=count)


def decide_alerts(
    *,
    state: State,
    claude_window: Optional[LatestWindow],
    codex: Optional[ProbeResult],
    now: float,
    claude_threshold: int,
    codex_threshold_percent: int,
) -> list[AlertDecision]:
    decisions: list[AlertDecision] = []

    if claude_window is not None:
        if (
            claude_window.count >= claude_threshold
            and claude_window.reset > now
            and state.claude.alerted_for_reset != int(claude_window.reset)
        ):
            decisions.append(AlertDecision(source="claude", reset_at=int(claude_window.reset)))

    if codex is not None:
        used_percent = int(codex.extra.get("used_percent", 0) or 0)
        reset_at = codex.extra.get("reset_at")
        if (
            reset_at is not None
            and used_percent >= codex_threshold_percent
            and state.codex.cooldown_until <= now
            and state.codex.alerted_for_reset != int(reset_at)
        ):
            decisions.append(AlertDecision(source="codex", reset_at=int(reset_at)))

    return decisions
```

- [ ] **Step 4: Fix existing tests that assume no correction**

Update existing tests in `tests/test_window.py` that compare `reset` values — they now need to account for `RESET_CORRECTION_SECONDS`. Either:
- Pass `correction=0.0` explicitly in tests that test pure windowing logic
- Or adjust expected values to include the -360 offset

Recommended: pass `correction=0.0` in the existing tests to isolate windowing logic:

```python
def test_single_timestamp_opens_first_window():
    w = replay_windows((1000.0,), correction=0.0)
    assert w == LatestWindow(start=1000.0, reset=1000.0 + WINDOW_SECONDS, count=1)
```

Apply this pattern to all existing `replay_windows` calls in the test file.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/test_window.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/core/window.py tests/test_window.py
git commit -m "feat(window): add correction parameter, default -360s"
```

---

### Task 4: Precise Probe Module

**Files:**
- Create: `quota_monitor/probes/precise.py`
- Create: `tests/test_precise_probe.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_precise_probe.py
import json
import time

from quota_monitor.probes.precise import PreciseUsage, read_precise


def _write_cache(tmp_path, data):
    path = tmp_path / "rate_limits_cache.json"
    path.write_text(json.dumps(data))
    return path


def test_read_precise_returns_none_if_missing(tmp_path):
    result = read_precise(tmp_path / "missing.json", now=time.time())
    assert result is None


def test_read_precise_returns_none_if_malformed(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("not json")
    assert read_precise(path, now=time.time()) is None


def test_read_precise_returns_none_if_five_hour_expired(tmp_path):
    now = 2000.0
    path = _write_cache(tmp_path, {
        "captured_at": 1000.0,
        "five_hour": {"used_percentage": 50.0, "resets_at": 1500.0},
        "seven_day": {"used_percentage": 20.0, "resets_at": 9999.0},
    })
    assert read_precise(path, now=now) is None


def test_read_precise_returns_none_if_captured_too_old(tmp_path):
    now = 30000.0
    path = _write_cache(tmp_path, {
        "captured_at": 1000.0,  # 29000s ago > 6h
        "five_hour": {"used_percentage": 50.0, "resets_at": 99999.0},
        "seven_day": {"used_percentage": 20.0, "resets_at": 99999.0},
    })
    assert read_precise(path, now=now) is None


def test_read_precise_returns_usage_when_valid(tmp_path):
    now = 1000.0
    path = _write_cache(tmp_path, {
        "captured_at": 900.0,
        "five_hour": {"used_percentage": 42.5, "resets_at": 5000.0},
        "seven_day": {"used_percentage": 15.0, "resets_at": 99999.0},
    })
    result = read_precise(path, now=now)
    assert result is not None
    assert isinstance(result, PreciseUsage)
    assert result.five_hour_pct == 42.5
    assert result.five_hour_resets_at == 5000.0
    assert result.seven_day_pct == 15.0
    assert result.seven_day_resets_at == 99999.0
    assert result.captured_at == 900.0


def test_read_precise_tolerates_missing_seven_day(tmp_path):
    now = 1000.0
    path = _write_cache(tmp_path, {
        "captured_at": 900.0,
        "five_hour": {"used_percentage": 42.5, "resets_at": 5000.0},
    })
    result = read_precise(path, now=now)
    assert result is not None
    assert result.seven_day_pct == 0.0
    assert result.seven_day_resets_at == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_precise_probe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quota_monitor.probes.precise'`

- [ ] **Step 3: Write implementation**

```python
# quota_monitor/probes/precise.py
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

MAX_CACHE_AGE_SECONDS = 6 * 3600


@dataclass(frozen=True)
class PreciseUsage:
    five_hour_pct: float
    five_hour_resets_at: float
    seven_day_pct: float
    seven_day_resets_at: float
    captured_at: float


def read_precise(cache_path: Path, *, now: float) -> Optional[PreciseUsage]:
    if not cache_path.exists():
        return None
    try:
        raw = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    captured_at = raw.get("captured_at", 0)
    if now - captured_at > MAX_CACHE_AGE_SECONDS:
        return None

    five_hour = raw.get("five_hour")
    if not five_hour:
        return None

    resets_at = five_hour.get("resets_at", 0)
    if resets_at <= now:
        return None

    seven_day = raw.get("seven_day") or {}
    return PreciseUsage(
        five_hour_pct=float(five_hour.get("used_percentage", 0)),
        five_hour_resets_at=float(resets_at),
        seven_day_pct=float(seven_day.get("used_percentage", 0)),
        seven_day_resets_at=float(seven_day.get("resets_at", 0)),
        captured_at=float(captured_at),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_precise_probe.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/probes/precise.py tests/test_precise_probe.py
git commit -m "feat(probes): add precise probe reading rate_limits_cache"
```

---

### Task 5: StatusLine Wrapper

**Files:**
- Create: `quota_monitor/statusline/__init__.py`
- Create: `quota_monitor/statusline/__main__.py`
- Create: `quota_monitor/statusline/wrapper.py`
- Create: `tests/test_statusline_wrapper.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_statusline_wrapper.py
import json
import sys
from pathlib import Path
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
        "original": {"type": "command", "command": "~/.open-island/bin/oi-statusline", "refreshInterval": 5}
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
    # Use echo as the "original" command
    orig_path.write_text(json.dumps({"original": "echo HELLO"}))
    with patch("sys.stdin") as mock_stdin:
        mock_stdin.read.return_value = SAMPLE_STDIN
        rc = run_wrapper(cache_path=cache_path, original_path=orig_path)
    assert rc == 0
    captured = capsys.readouterr()
    assert "HELLO" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_statusline_wrapper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quota_monitor.statusline'`

- [ ] **Step 3: Create package and implementation**

```python
# quota_monitor/statusline/__init__.py
```

```python
# quota_monitor/statusline/__main__.py
import sys
from pathlib import Path


def main() -> int:
    from .wrapper import run_wrapper

    data_dir = Path.home() / ".quota-monitor"
    return run_wrapper(
        cache_path=data_dir / "rate_limits_cache.json",
        original_path=data_dir / "statusline_original.json",
    )


if __name__ == "__main__":
    sys.exit(main())
```

```python
# quota_monitor/statusline/wrapper.py
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def extract_and_cache_rate_limits(raw_stdin: str, cache_path: Path) -> None:
    try:
        data = json.loads(raw_stdin)
    except (json.JSONDecodeError, TypeError):
        return
    rate_limits = data.get("rate_limits")
    if not rate_limits:
        return
    payload = {"captured_at": time.time()}
    if "five_hour" in rate_limits:
        payload["five_hour"] = rate_limits["five_hour"]
    if "seven_day" in rate_limits:
        payload["seven_day"] = rate_limits["seven_day"]
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, cache_path)
    except OSError:
        pass


def load_original_command(original_path: Path) -> Optional[str]:
    if not original_path.exists():
        return None
    try:
        raw = json.loads(original_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    original = raw.get("original")
    if original is None:
        return None
    if isinstance(original, dict):
        return original.get("command")
    if isinstance(original, str):
        return original
    return None


def run_wrapper(*, cache_path: Path, original_path: Path) -> int:
    raw_stdin = sys.stdin.read()

    extract_and_cache_rate_limits(raw_stdin, cache_path)

    command = load_original_command(original_path)
    if command:
        try:
            result = subprocess.run(
                command,
                input=raw_stdin,
                capture_output=True,
                text=True,
                timeout=5,
                shell=True,
            )
            sys.stdout.write(result.stdout)
        except (subprocess.TimeoutExpired, OSError):
            pass
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_statusline_wrapper.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/statusline/ tests/test_statusline_wrapper.py
git commit -m "feat(statusline): add wrapper for rate_limits caching"
```

---

### Task 6: StatusLine Installer

**Files:**
- Create: `quota_monitor/statusline/installer.py`
- Create: `tests/test_statusline_installer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_statusline_installer.py
import json

from quota_monitor.statusline.installer import (
    detect_existing_statusline,
    install_wrapper,
    uninstall_wrapper,
    is_our_wrapper,
    StatusLineState,
)


def _write_settings(tmp_path, settings_data):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(settings_data))
    return path


def test_detect_no_statusline(tmp_path):
    settings_path = _write_settings(tmp_path, {"permissions": {}})
    result = detect_existing_statusline(settings_path)
    assert result == StatusLineState.NONE


def test_detect_our_wrapper(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"}
    })
    result = detect_existing_statusline(settings_path)
    assert result == StatusLineState.OUR_WRAPPER


def test_detect_third_party_object(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "~/.open-island/bin/oi-statusline"}
    })
    result = detect_existing_statusline(settings_path)
    assert result == StatusLineState.THIRD_PARTY


def test_detect_third_party_string(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": "npx ccstatusline@latest"
    })
    result = detect_existing_statusline(settings_path)
    assert result == StatusLineState.THIRD_PARTY


def test_is_our_wrapper():
    assert is_our_wrapper({"type": "command", "command": "python3 -m quota_monitor.statusline"})
    assert is_our_wrapper("python3 -m quota_monitor.statusline --foo")
    assert not is_our_wrapper("~/.open-island/bin/oi-statusline")
    assert not is_our_wrapper({"type": "command", "command": "node /path/to/hud.js"})
    assert not is_our_wrapper(None)


def test_install_wrapper_fresh(tmp_path):
    settings_path = _write_settings(tmp_path, {"permissions": {}})
    backup_path = tmp_path / "statusline_original.json"

    install_wrapper(settings_path=settings_path, backup_path=backup_path)

    settings = json.loads(settings_path.read_text())
    assert "quota_monitor.statusline" in settings["statusLine"]["command"]
    backup = json.loads(backup_path.read_text())
    assert backup["original"] is None


def test_install_wrapper_wraps_existing(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "~/.open-island/bin/oi", "padding": 2}
    })
    backup_path = tmp_path / "statusline_original.json"

    install_wrapper(settings_path=settings_path, backup_path=backup_path)

    settings = json.loads(settings_path.read_text())
    assert "quota_monitor.statusline" in settings["statusLine"]["command"]
    assert settings["statusLine"]["padding"] == 2  # preserved
    backup = json.loads(backup_path.read_text())
    assert backup["original"]["command"] == "~/.open-island/bin/oi"


def test_uninstall_wrapper_restores(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"},
        "permissions": {"allow": []}
    })
    backup_path = tmp_path / "statusline_original.json"
    backup_path.write_text(json.dumps({
        "original": {"type": "command", "command": "~/.open-island/bin/oi", "padding": 2}
    }))

    restored = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
    assert restored is True

    settings = json.loads(settings_path.read_text())
    assert settings["statusLine"]["command"] == "~/.open-island/bin/oi"
    assert settings["permissions"] == {"allow": []}  # other fields untouched


def test_uninstall_wrapper_removes_key_if_original_null(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"},
        "permissions": {"allow": []}
    })
    backup_path = tmp_path / "statusline_original.json"
    backup_path.write_text(json.dumps({"original": None}))

    restored = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
    assert restored is True

    settings = json.loads(settings_path.read_text())
    assert "statusLine" not in settings


def test_uninstall_skips_if_not_our_wrapper(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "node /custom/hud.js"}
    })
    backup_path = tmp_path / "statusline_original.json"
    backup_path.write_text(json.dumps({"original": "old_thing"}))

    restored = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
    assert restored is False

    settings = json.loads(settings_path.read_text())
    assert settings["statusLine"]["command"] == "node /custom/hud.js"


def test_uninstall_skips_if_no_backup(tmp_path):
    settings_path = _write_settings(tmp_path, {
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"}
    })
    backup_path = tmp_path / "missing_backup.json"

    restored = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
    assert restored is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_statusline_installer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quota_monitor.statusline.installer'`

- [ ] **Step 3: Write implementation**

```python
# quota_monitor/statusline/installer.py
import enum
import json
import os
from pathlib import Path
from typing import Optional

WRAPPER_MARKER = "quota_monitor.statusline"


class StatusLineState(enum.Enum):
    NONE = "none"
    OUR_WRAPPER = "our_wrapper"
    THIRD_PARTY = "third_party"


def is_our_wrapper(statusline_value) -> bool:
    if statusline_value is None:
        return False
    if isinstance(statusline_value, str):
        return WRAPPER_MARKER in statusline_value
    if isinstance(statusline_value, dict):
        cmd = statusline_value.get("command", "")
        return WRAPPER_MARKER in (cmd or "")
    return False


def detect_existing_statusline(settings_path: Path) -> StatusLineState:
    if not settings_path.exists():
        return StatusLineState.NONE
    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return StatusLineState.NONE
    sl = settings.get("statusLine")
    if sl is None:
        return StatusLineState.NONE
    if is_our_wrapper(sl):
        return StatusLineState.OUR_WRAPPER
    return StatusLineState.THIRD_PARTY


def _get_command_from_statusline(sl) -> Optional[str]:
    if isinstance(sl, str):
        return sl
    if isinstance(sl, dict):
        return sl.get("command")
    return None


def install_wrapper(*, settings_path: Path, backup_path: Path) -> None:
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            settings = {}

    original_sl = settings.get("statusLine")

    # Backup original value
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps({"original": original_sl}))

    # Build new statusLine
    new_sl = {
        "type": "command",
        "command": "python3 -m quota_monitor.statusline",
        "refreshInterval": 5,
    }
    # Preserve existing fields from original object form
    if isinstance(original_sl, dict):
        for key in ("padding", "hideVimModeIndicator"):
            if key in original_sl:
                new_sl[key] = original_sl[key]
        if "refreshInterval" in original_sl:
            new_sl["refreshInterval"] = original_sl["refreshInterval"]

    settings["statusLine"] = new_sl

    tmp = settings_path.with_suffix(settings_path.suffix + ".tmp")
    tmp.write_text(json.dumps(settings, indent=2))
    os.replace(tmp, settings_path)


def uninstall_wrapper(*, settings_path: Path, backup_path: Path) -> bool:
    if not backup_path.exists():
        return False
    if not settings_path.exists():
        return False

    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    current_sl = settings.get("statusLine")
    if not is_our_wrapper(current_sl):
        return False

    try:
        backup = json.loads(backup_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    original = backup.get("original")
    if original is None:
        settings.pop("statusLine", None)
    else:
        settings["statusLine"] = original

    tmp = settings_path.with_suffix(settings_path.suffix + ".tmp")
    tmp.write_text(json.dumps(settings, indent=2))
    os.replace(tmp, settings_path)
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_statusline_installer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/statusline/installer.py tests/test_statusline_installer.py
git commit -m "feat(statusline): add installer for safe install/uninstall"
```

---

### Task 7: i18n Messages

**Files:**
- Modify: `quota_monitor/i18n/messages/en.py`
- Modify: `quota_monitor/i18n/messages/zh.py`
- Modify: `tests/test_i18n.py` (if exists, or create)

- [ ] **Step 1: Write failing test**

```python
# Append to tests/test_i18n.py (or create if not exists)
from quota_monitor.i18n import t, set_locale


def test_statusline_wizard_keys_exist_en():
    set_locale("en")
    assert "[missing" not in t("wizard.statusline.title")
    assert "[missing" not in t("wizard.statusline.enable_fresh")
    assert "[missing" not in t("wizard.statusline.enable_existing", cmd_preview="test")
    assert "[missing" not in t("wizard.statusline.already_configured")


def test_statusline_wizard_keys_exist_zh():
    set_locale("zh")
    assert "[missing" not in t("wizard.statusline.title")
    assert "[missing" not in t("wizard.statusline.enable_fresh")
    assert "[missing" not in t("wizard.statusline.enable_existing", cmd_preview="test")
    assert "[missing" not in t("wizard.statusline.already_configured")


def test_uninstall_statusline_keys():
    set_locale("en")
    assert "[missing" not in t("uninstall.statusline.restored")
    assert "[missing" not in t("uninstall.statusline.skipped_manual")
    assert "[missing" not in t("uninstall.statusline.verify_cmd")
    set_locale("zh")
    assert "[missing" not in t("uninstall.statusline.restored")
    assert "[missing" not in t("uninstall.statusline.skipped_manual")


def test_alert_suffix_keys():
    set_locale("en")
    assert "[missing" not in t("alert.suffix.estimated")
    set_locale("zh")
    assert "[missing" not in t("alert.suffix.estimated")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_i18n.py::test_statusline_wizard_keys_exist_en tests/test_i18n.py::test_uninstall_statusline_keys tests/test_i18n.py::test_alert_suffix_keys -v`
Expected: FAIL (keys missing)

- [ ] **Step 3: Add messages to en.py**

Append to the `MESSAGES` dict in `quota_monitor/i18n/messages/en.py`:

```python
    # StatusLine wizard
    "wizard.statusline.title": "\n=== ({step}) StatusLine Precise Usage Tracking ===",
    "wizard.statusline.enable_fresh": "Enable statusLine usage tracking? A lightweight script will read real-time quota data from Claude Code.",
    "wizard.statusline.enable_existing": "Detected custom status line tool (`{cmd_preview}`). Allow wrapping it to capture precise quota data? (Your existing tool's display will not be affected)",
    "wizard.statusline.already_configured": "StatusLine wrapper already configured. Skipping.",
    "wizard.statusline.installed": "✓ StatusLine wrapper installed.",

    # StatusLine uninstall
    "uninstall.statusline.restored": "✓ StatusLine wrapper removed. Original status line restored.",
    "uninstall.statusline.skipped_manual": "StatusLine has been manually changed since install. Skipping restore.",
    "uninstall.statusline.skipped_no_backup": "No statusLine backup found. Skipping restore.",
    "uninstall.statusline.verify_cmd": "  To verify: cat ~/.claude/settings.json | jq .statusLine",

    # Alert suffix
    "alert.suffix.estimated": " (estimated from local conversation logs)",
```

- [ ] **Step 4: Add messages to zh.py**

Append to the `MESSAGES` dict in `quota_monitor/i18n/messages/zh.py`:

```python
    # StatusLine 向导
    "wizard.statusline.title": "\n=== ({step}) StatusLine 精确用量追踪 ===",
    "wizard.statusline.enable_fresh": "是否启用 StatusLine 精确用量追踪？将配置一个轻量脚本读取 Claude Code 的实时额度信息。",
    "wizard.statusline.enable_existing": "检测到已安装自定义状态栏工具（`{cmd_preview}`）。是否同意包装一层以获取精确用量信息？（不会影响现有状态栏工具的显示效果）",
    "wizard.statusline.already_configured": "StatusLine wrapper 已配置，跳过。",
    "wizard.statusline.installed": "✓ StatusLine wrapper 已安装。",

    # StatusLine 卸载
    "uninstall.statusline.restored": "✓ StatusLine wrapper 已移除，原状态栏配置已恢复。",
    "uninstall.statusline.skipped_manual": "检测到 statusLine 已被手动更改，跳过还原。",
    "uninstall.statusline.skipped_no_backup": "未找到 statusLine 备份，跳过还原。",
    "uninstall.statusline.verify_cmd": "  检查命令: cat ~/.claude/settings.json | jq .statusLine",

    # 报警后缀
    "alert.suffix.estimated": "（根据本地对话记录时间估算）",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_i18n.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/i18n/messages/en.py quota_monitor/i18n/messages/zh.py tests/test_i18n.py
git commit -m "feat(i18n): add statusline wizard, uninstall, and alert suffix messages"
```

---

### Task 8: Integrate Precise/Estimated Decision into run_once

**Files:**
- Modify: `quota_monitor/cli/run.py`
- Modify: `tests/test_cli_run.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_cli_run.py`:

```python
import json
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_run_once_uses_precise_when_cache_valid(tmp_path, monkeypatch):
    """When rate_limits_cache has a valid, unexpired five_hour entry,
    run_once should use precise reset_at instead of replay_windows."""
    from quota_monitor.cli.run import run_once

    # Setup config
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'locale = "en"\nlog_level = "info"\n\n'
        '[probes.claude]\nenabled = true\nthreshold_turns = 5\nwindow_hours = 5\n\n'
        '[probes.codex]\nenabled = false\nthreshold_percent = 30\n\n'
        '[notifiers]\nprimary = "macos_native"\nfallback = ""\n\n'
        '[notifiers.telegram]\n[notifiers.cloudflare_relay]\nenabled = false\nwebhook_url = ""\n\n'
        '[keepalive]\nenabled = false\nmodel = "haiku"\nphrase_pool = []\n'
        'seamless_trigger_minutes = 30\nseamless_buffer_seconds = 60\n'
    )
    env_path = tmp_path / ".env"
    env_path.write_text("")
    state_path = tmp_path / "state.json"
    cache_path = tmp_path / "rate_limits_cache.json"
    calibration_path = tmp_path / "calibration.json"

    now = 10000.0
    # Write a valid cache: five_hour resets in the future
    cache_path.write_text(json.dumps({
        "captured_at": now - 60,
        "five_hour": {"used_percentage": 80.0, "resets_at": now + 3600},
        "seven_day": {"used_percentage": 30.0, "resets_at": now + 86400},
    }))

    with patch("quota_monitor.cli.run.platform_paths") as mock_paths:
        mock_paths.claude_app_dir.return_value = tmp_path / "app"
        mock_paths.claude_cli_dir.return_value = tmp_path / "cli"
        mock_paths.claude_costs_file.return_value = tmp_path / "costs.jsonl"
        mock_paths.codex_auth_file.return_value = tmp_path / "auth.json"
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = calibration_path
        (tmp_path / "app").mkdir()
        (tmp_path / "cli").mkdir()

        rc = run_once(
            config_path=config_path,
            env_path=env_path,
            state_path=state_path,
            now=now,
            dry_run=True,
        )
    assert rc == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_run.py::test_run_once_uses_precise_when_cache_valid -v`
Expected: FAIL (run_once doesn't import or use rate_limits_cache yet)

- [ ] **Step 3: Modify run_once to integrate precise probe and calibration**

Update `quota_monitor/cli/run.py` — add imports and modify the logic between probe scan and decide_alerts:

```python
# Add to imports at top:
from ..core.calibration import load_calibration, record_sample, save_calibration
from ..probes.precise import read_precise

# In run_once(), after scanning claude_result and codex_result, replace the
# section that computes claude_window with:

    # --- Precise vs Estimated decision ---
    precise = None
    if cfg.probes.claude.enabled:
        precise = read_precise(platform_paths.rate_limits_cache(), now=now)

    calibration_state = load_calibration(platform_paths.calibration_file())
    source_type = None

    if precise is not None:
        # Precise mode: use statusLine's exact values
        from ..core.window import LatestWindow
        claude_window = LatestWindow(
            start=precise.five_hour_resets_at - (cfg.probes.claude.window_hours * 3600),
            reset=precise.five_hour_resets_at,
            count=cfg.probes.claude.threshold_turns,  # force threshold met when precise
        )
        source_type = "precise"

        # Calibration sampling: compare with replay_windows if possible
        if claude_result is not None:
            computed = replay_windows(claude_result.timestamps, correction=0.0)
            if computed is not None and computed.reset > now:
                diff = abs(precise.five_hour_resets_at - computed.reset)
                if diff < 1800:
                    calibration_state = record_sample(
                        calibration_state,
                        precise_reset=precise.five_hour_resets_at,
                        computed_reset=computed.reset,
                        ts=now,
                    )
                    save_calibration(platform_paths.calibration_file(), calibration_state)
    else:
        # Estimated mode: use replay_windows with calibrated correction
        claude_window = (
            replay_windows(
                claude_result.timestamps,
                correction=calibration_state.current_correction_seconds,
            )
            if claude_result is not None
            else None
        )
        source_type = "estimated" if claude_window is not None else None
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS (existing tests may need minor patches for new imports)

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/cli/run.py tests/test_cli_run.py
git commit -m "feat(run): integrate precise/estimated decision and calibration sampling"
```

---

### Task 9: Setup Wizard StatusLine Step

**Files:**
- Modify: `quota_monitor/cli/setup.py`
- Create: `tests/test_wizard_statusline.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_wizard_statusline.py
import json
from unittest.mock import patch
from pathlib import Path

from quota_monitor.cli.setup import _statusline_wizard_step


def test_statusline_step_fresh_install_accept(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"permissions": {}}))
    backup_path = tmp_path / "statusline_original.json"

    with patch("quota_monitor.cli.setup.ask_yes_no", return_value=True):
        _statusline_wizard_step(
            settings_path=settings_path,
            backup_path=backup_path,
        )

    settings = json.loads(settings_path.read_text())
    assert "quota_monitor.statusline" in settings["statusLine"]["command"]
    assert backup_path.exists()


def test_statusline_step_fresh_install_decline(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"permissions": {}}))
    backup_path = tmp_path / "statusline_original.json"

    with patch("quota_monitor.cli.setup.ask_yes_no", return_value=False):
        _statusline_wizard_step(
            settings_path=settings_path,
            backup_path=backup_path,
        )

    settings = json.loads(settings_path.read_text())
    assert "statusLine" not in settings
    assert not backup_path.exists()


def test_statusline_step_existing_tool_accept(tmp_path):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "~/.open-island/bin/oi"}
    }))
    backup_path = tmp_path / "statusline_original.json"

    with patch("quota_monitor.cli.setup.ask_yes_no", return_value=True):
        _statusline_wizard_step(
            settings_path=settings_path,
            backup_path=backup_path,
        )

    settings = json.loads(settings_path.read_text())
    assert "quota_monitor.statusline" in settings["statusLine"]["command"]
    backup = json.loads(backup_path.read_text())
    assert backup["original"]["command"] == "~/.open-island/bin/oi"


def test_statusline_step_already_configured(tmp_path, capsys):
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"}
    }))
    backup_path = tmp_path / "statusline_original.json"

    _statusline_wizard_step(
        settings_path=settings_path,
        backup_path=backup_path,
    )

    captured = capsys.readouterr()
    assert "already configured" in captured.out.lower() or "已配置" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_wizard_statusline.py -v`
Expected: FAIL with `ImportError: cannot import name '_statusline_wizard_step'`

- [ ] **Step 3: Add _statusline_wizard_step function to setup.py**

Add to `quota_monitor/cli/setup.py`:

```python
from ..statusline.installer import (
    detect_existing_statusline,
    install_wrapper,
    StatusLineState,
)


def _statusline_wizard_step(*, settings_path: Path, backup_path: Path) -> None:
    state = detect_existing_statusline(settings_path)

    if state == StatusLineState.OUR_WRAPPER:
        print(t("wizard.statusline.already_configured"))
        return

    if state == StatusLineState.NONE:
        prompt = t("wizard.statusline.enable_fresh")
    else:
        # Extract command preview (first 30 chars)
        try:
            settings = json.loads(settings_path.read_text())
            sl = settings.get("statusLine", "")
            if isinstance(sl, dict):
                cmd_preview = (sl.get("command") or "")[:30]
            else:
                cmd_preview = str(sl)[:30]
        except (json.JSONDecodeError, OSError):
            cmd_preview = "unknown"
        prompt = t("wizard.statusline.enable_existing", cmd_preview=cmd_preview)

    if ask_yes_no(prompt, default=True):
        install_wrapper(settings_path=settings_path, backup_path=backup_path)
        print(t("wizard.statusline.installed"))
```

Also add `import json` at top if not already present, and integrate the call in `_collect_interactive_answers` before the schedule step:

```python
    # Add before wizard.step7.title
    print(t("wizard.statusline.title", step="N/N"))
    from ..platform import paths as platform_paths
    _statusline_wizard_step(
        settings_path=platform_paths.claude_settings_file(),
        backup_path=platform_paths.statusline_original(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_wizard_statusline.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/cli/setup.py tests/test_wizard_statusline.py
git commit -m "feat(wizard): add statusLine detection and install step"
```

---

### Task 10: Uninstall Safe Restore

**Files:**
- Modify: `quota_monitor/cli/uninstall.py`
- Modify: `tests/test_cli_uninstall.py`

- [ ] **Step 1: Write failing test**

```python
# Append to tests/test_cli_uninstall.py (or create)
import json
from pathlib import Path
from unittest.mock import patch

from quota_monitor.cli.uninstall import uninstall


def test_uninstall_restores_statusline(tmp_path, capsys):
    plist_path = tmp_path / "agent.plist"
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "statusLine": {"type": "command", "command": "python3 -m quota_monitor.statusline"},
        "other": "preserved",
    }))
    backup_path = tmp_path / "statusline_original.json"
    backup_path.write_text(json.dumps({"original": {"type": "command", "command": "echo hi"}}))
    cache_path = tmp_path / "rate_limits_cache.json"
    cache_path.write_text("{}")
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text("{}")

    with patch("quota_monitor.cli.uninstall.platform_paths") as mock_paths:
        mock_paths.claude_settings_file.return_value = settings_path
        mock_paths.statusline_original.return_value = backup_path
        mock_paths.rate_limits_cache.return_value = cache_path
        mock_paths.calibration_file.return_value = calibration_path

        rc = uninstall(launch_agent_label="test", plist_path=plist_path)

    assert rc == 0
    settings = json.loads(settings_path.read_text())
    assert settings["statusLine"]["command"] == "echo hi"
    assert settings["other"] == "preserved"
    assert not cache_path.exists()
    assert not backup_path.exists()
    assert not calibration_path.exists()
    captured = capsys.readouterr()
    assert "restored" in captured.out.lower() or "已恢复" in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_uninstall.py::test_uninstall_restores_statusline -v`
Expected: FAIL (uninstall doesn't handle statusLine yet)

- [ ] **Step 3: Modify uninstall.py**

```python
# quota_monitor/cli/uninstall.py
from pathlib import Path

from ..i18n import t
from ..platform import paths as platform_paths
from ..platform.schedule import uninstall_launch_agent
from ..statusline.installer import uninstall_wrapper


def uninstall(*, launch_agent_label: str, plist_path: Path) -> int:
    if plist_path.exists():
        uninstall_launch_agent(plist_path=plist_path)
        print(f"removed LaunchAgent: {plist_path}")
    else:
        print(f"no LaunchAgent at {plist_path} — nothing to do")

    # StatusLine restore
    settings_path = platform_paths.claude_settings_file()
    backup_path = platform_paths.statusline_original()
    if backup_path.exists():
        restored = uninstall_wrapper(settings_path=settings_path, backup_path=backup_path)
        if restored:
            print(t("uninstall.statusline.restored"))
            print(t("uninstall.statusline.verify_cmd"))
        else:
            print(t("uninstall.statusline.skipped_manual"))
    else:
        # No backup means statusLine was never installed by us — silent skip
        pass

    # Clean up statusLine-related files
    for path in (
        platform_paths.rate_limits_cache(),
        platform_paths.statusline_original(),
        platform_paths.calibration_file(),
    ):
        if path.exists():
            path.unlink()

    print("NOTE: ~/.quota-monitor/ (config.toml, .env, state.json) was NOT touched.")
    print("      Remove manually if you want a complete wipe.")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cli_uninstall.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/cli/uninstall.py tests/test_cli_uninstall.py
git commit -m "feat(uninstall): add safe statusLine restore and cache cleanup"
```

---

### Task 11: README Documentation

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`

- [ ] **Step 1: Add StatusLine section to README.md**

After the existing "Setup" section, add:

```markdown
## StatusLine Precise Usage Tracking (Optional)

quota-monitor can read real-time quota data directly from Claude Code via its [statusLine](https://docs.anthropic.com/en/docs/claude-code/status-line) mechanism, giving you precise 5-hour and 7-day usage percentages and exact reset times.

### How it works

1. The setup wizard configures a lightweight Python wrapper as your Claude Code statusLine command
2. Each time Claude Code updates its status bar, the wrapper:
   - Extracts `rate_limits` from the JSON payload
   - Writes it to a local cache (`~/.quota-monitor/rate_limits_cache.json`)
   - Forwards everything to your original statusLine tool (if any)
   - Returns the original output unchanged
3. When quota-monitor runs its periodic scan, it checks the cache first:
   - **Cache valid** → uses precise values (exact percentage and reset time)
   - **Cache expired** → falls back to local file replay estimation

### Compatibility

The wrapper is designed to work alongside existing statusLine tools:
- **Open Island** — detected and wrapped automatically
- **Claude HUD** — detected and wrapped automatically
- **ccstatusline** — detected and wrapped automatically
- **Custom scripts** — any existing `statusLine` config is preserved

### Manual install/uninstall

```bash
# Install (also available via `quota-monitor setup`)
quota-monitor statusline install

# Uninstall (also part of `quota-monitor uninstall`)
quota-monitor statusline uninstall
```

### Precise vs Estimated notifications

- Precise (from statusLine): "Quota resets at 15:30"
- Estimated (from local logs): "Quota resets at 15:30 (estimated from local conversation logs)"
```

- [ ] **Step 2: Add equivalent section to README.zh-CN.md**

```markdown
## StatusLine 精确用量追踪（可选）

quota-monitor 可以通过 Claude Code 的 [statusLine](https://docs.anthropic.com/en/docs/claude-code/status-line) 机制直接读取实时额度数据，获取精确的 5 小时和 7 天使用百分比及重置时间。

### 工作原理

1. 配置向导会将一个轻量 Python wrapper 设置为你的 Claude Code statusLine 命令
2. 每次 Claude Code 更新状态栏时，wrapper 会：
   - 从 JSON 数据中提取 `rate_limits`
   - 写入本地缓存（`~/.quota-monitor/rate_limits_cache.json`）
   - 将所有内容转发给原始 statusLine 工具（如有）
   - 原样返回原始输出
3. quota-monitor 定时扫描时，优先检查缓存：
   - **缓存有效** → 使用精确值（确切百分比和重置时间）
   - **缓存过期** → 回退到本地文件重放估算

### 兼容性

wrapper 可与现有 statusLine 工具共存：
- **Open Island** — 自动检测并包装
- **Claude HUD** — 自动检测并包装
- **ccstatusline** — 自动检测并包装
- **自定义脚本** — 任何现有 `statusLine` 配置均会保留

### 手动安装/卸载

```bash
# 安装（也可通过 `quota-monitor setup` 完成）
quota-monitor statusline install

# 卸载（也包含在 `quota-monitor uninstall` 中）
quota-monitor statusline uninstall
```

### 精确值 vs 估算值通知

- 精确值（来自 statusLine）：「额度将于 15:30 恢复」
- 估算值（来自本地日志）：「额度将于 15:30 恢复（根据本地对话记录时间估算）」
```

- [ ] **Step 3: Commit**

```bash
git add README.md README.zh-CN.md
git commit -m "docs: add StatusLine precise usage tracking section"
```

---

## Execution Order & Dependencies

```
Task 1 (paths) ─────────────────────────────────────┐
Task 2 (calibration) ──────────────────────────────┐ │
Task 3 (window.py) ────────────────────────────────┤ │
Task 4 (precise probe) ───────────────────────────┐│ │
Task 5 (wrapper) ─────────────────────────────────┐││ │
Task 6 (installer) ───────────────────────────────┤│││
Task 7 (i18n) ────────────────────────────────────┤│││
                                                   ││││
Task 8 (run.py integration) ──── depends on 1-4 ──┘│││
Task 9 (setup wizard) ──── depends on 6-7 ─────────┘││
Task 10 (uninstall) ──── depends on 6-7 ────────────┘│
Task 11 (README) ──── depends on all above ───────────┘
```

Tasks 1-7 can be executed in any order. Tasks 8-11 have the dependencies shown above.
