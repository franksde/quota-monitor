import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_CORRECTION_SECONDS = -300
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
    samples: list[Sample] = field(default_factory=list)


def load_calibration(path: Path) -> CalibrationState:
    if not path.exists():
        return CalibrationState()
    try:
        raw = json.loads(path.read_text())
        samples = [Sample(**s) for s in raw.get("samples", [])]
        return CalibrationState(
            current_correction_seconds=raw.get(
                "current_correction_seconds",
                DEFAULT_CORRECTION_SECONDS,
            ),
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
