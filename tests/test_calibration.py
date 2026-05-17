from quota_monitor.core.calibration import (
    CalibrationState,
    Sample,
    load_calibration,
    save_calibration,
    compute_correction,
    record_sample,
    DEFAULT_CORRECTION_SECONDS,
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
        Sample(ts=i, precise_reset=1000 + i, computed_reset=1000 + i + 360, drift=-360)
        for i in range(5)
    ]
    result = compute_correction(samples)
    assert abs(result - (-360)) < 1


def test_compute_correction_weights_recent_samples_more():
    samples = [
        Sample(ts=1, precise_reset=100, computed_reset=460, drift=-360),
        Sample(ts=2, precise_reset=200, computed_reset=560, drift=-360),
        Sample(ts=3, precise_reset=300, computed_reset=660, drift=-360),
        Sample(ts=4, precise_reset=400, computed_reset=700, drift=-300),
        Sample(ts=5, precise_reset=500, computed_reset=800, drift=-300),
    ]
    result = compute_correction(samples)
    assert result > -360
    assert result < -300


def test_compute_correction_excludes_outliers():
    samples = [
        Sample(ts=1, precise_reset=100, computed_reset=460, drift=-360),
        Sample(ts=2, precise_reset=200, computed_reset=560, drift=-360),
        Sample(ts=3, precise_reset=300, computed_reset=660, drift=-360),
        Sample(ts=4, precise_reset=400, computed_reset=2400, drift=-2000),
    ]
    result = compute_correction(samples)
    assert abs(result - (-360)) < 1
    assert abs(samples[-1].drift) > OUTLIER_THRESHOLD_SECONDS


def test_record_sample_adds_and_truncates():
    state = CalibrationState(
        current_correction_seconds=-360.0,
        samples=[
            Sample(ts=i, precise_reset=i + 1000, computed_reset=i + 1360, drift=-360)
            for i in range(20)
        ],
    )
    new_state = record_sample(state, precise_reset=99999, computed_reset=100359, ts=21)
    assert len(new_state.samples) == MAX_SAMPLES
    assert new_state.samples[-1].ts == 21
    assert new_state.samples[0].ts == 1


def test_record_sample_recomputes_correction():
    state = CalibrationState(
        current_correction_seconds=-360.0,
        samples=[
            Sample(ts=i, precise_reset=i + 1000, computed_reset=i + 1360, drift=-360)
            for i in range(5)
        ],
    )
    new_state = record_sample(state, precise_reset=6000, computed_reset=6300, ts=6)
    assert new_state.current_correction_seconds > -360
