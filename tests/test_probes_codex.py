import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from quota_monitor.probes.codex import scan_codex, CodexAuthMissingError

FIXTURES = Path(__file__).parent / "fixtures" / "codex"


def _fake_response(payload: dict):
    fake = MagicMock()
    fake.read.return_value = json.dumps(payload).encode()
    fake.__enter__ = lambda self: fake
    fake.__exit__ = lambda self, *a: None
    return fake


def test_scan_returns_probe_result_with_extras(monkeypatch):
    payload = {"rate_limit": {"primary_window": {"used_percent": 45, "reset_at": 1747500000}}}
    with patch("quota_monitor.probes.codex.urlopen", return_value=_fake_response(payload)):
        result = scan_codex(auth_file=FIXTURES / "auth.json")
    assert result.source == "codex"
    assert result.timestamps == ()
    assert result.extra["used_percent"] == 45
    assert result.extra["reset_at"] == 1747500000


def test_missing_auth_raises(tmp_path):
    with pytest.raises(CodexAuthMissingError):
        scan_codex(auth_file=tmp_path / "nope.json")


def test_malformed_auth_raises(tmp_path):
    bad = tmp_path / "auth.json"
    bad.write_text("{not json")
    with pytest.raises(CodexAuthMissingError):
        scan_codex(auth_file=bad)


def test_missing_access_token_raises(tmp_path):
    bad = tmp_path / "auth.json"
    bad.write_text('{"tokens": {}}')
    with pytest.raises(CodexAuthMissingError):
        scan_codex(auth_file=bad)
