import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

import pytest
from quota_monitor.probes._throttled_fetch import FetchHint
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
        result = scan_codex(auth_file=FIXTURES / "auth.json", now=1_000.0)
    assert result.source == "codex"
    assert result.timestamps == ()
    assert result.extra["used_percent"] == 45
    assert result.extra["reset_at"] == 1747500000
    assert result.extra["fetched"] is True


def test_scan_uses_cached_hint_when_threshold_reached_and_reset_is_future():
    hint = FetchHint(last_fetch_at=1_000, last_used_percent=30, last_reset_at=2_000)
    with patch("quota_monitor.probes.codex.urlopen") as mock_urlopen:
        result = scan_codex(
            auth_file=FIXTURES / "auth.json",
            now=1_100.0,
            hint=hint,
            threshold_percent=30,
        )

    mock_urlopen.assert_not_called()
    assert result.source == "codex"
    assert result.extra == {
        "used_percent": 30,
        "reset_at": 2_000,
        "fetched": False,
    }


def test_scan_uses_cached_hint_when_far_from_threshold_and_interval_not_elapsed():
    hint = FetchHint(last_fetch_at=1_000, last_used_percent=5, last_reset_at=4_000)
    with patch("quota_monitor.probes.codex.urlopen") as mock_urlopen:
        result = scan_codex(
            auth_file=FIXTURES / "auth.json",
            now=2_199.0,
            hint=hint,
            threshold_percent=30,
        )

    mock_urlopen.assert_not_called()
    assert result.extra["used_percent"] == 5
    assert result.extra["reset_at"] == 4_000
    assert result.extra["fetched"] is False


def test_scan_fetches_when_far_from_threshold_and_interval_elapsed():
    hint = FetchHint(last_fetch_at=1_000, last_used_percent=5, last_reset_at=4_000)
    payload = {"rate_limit": {"primary_window": {"used_percent": 6, "reset_at": 4_000}}}
    with patch("quota_monitor.probes.codex.urlopen", return_value=_fake_response(payload)) as mock_urlopen:
        result = scan_codex(
            auth_file=FIXTURES / "auth.json",
            now=2_200.0,
            hint=hint,
            threshold_percent=30,
        )

    mock_urlopen.assert_called_once()
    assert result.extra["used_percent"] == 6
    assert result.extra["reset_at"] == 4_000
    assert result.extra["fetched"] is True


def test_scan_fetches_without_hint():
    payload = {"rate_limit": {"primary_window": {"used_percent": 6, "reset_at": 4_000}}}
    with patch("quota_monitor.probes.codex.urlopen", return_value=_fake_response(payload)) as mock_urlopen:
        result = scan_codex(auth_file=FIXTURES / "auth.json", now=1_000.0)

    mock_urlopen.assert_called_once()
    assert result.extra["used_percent"] == 6
    assert result.extra["reset_at"] == 4_000
    assert result.extra["fetched"] is True


def test_missing_auth_raises(tmp_path):
    with pytest.raises(CodexAuthMissingError):
        scan_codex(auth_file=tmp_path / "nope.json", now=1_000.0)


def test_malformed_auth_raises(tmp_path):
    bad = tmp_path / "auth.json"
    bad.write_text("{not json")
    with pytest.raises(CodexAuthMissingError):
        scan_codex(auth_file=bad, now=1_000.0)


def test_missing_access_token_raises(tmp_path):
    bad = tmp_path / "auth.json"
    bad.write_text('{"tokens": {}}')
    with pytest.raises(CodexAuthMissingError):
        scan_codex(auth_file=bad, now=1_000.0)


def test_uses_codex_auth_registry_active_account_when_usage_api_returns_401(tmp_path):
    auth = tmp_path / "auth.json"
    auth.write_text('{"tokens": {"access_token": "expired"}}')
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    (accounts / "registry.json").write_text(json.dumps({
        "active_account_key": "acct-active",
        "accounts": [
            {
                "account_key": "acct-old",
                "last_usage": {
                    "primary": {"used_percent": 99, "resets_at": 1_500},
                },
            },
            {
                "account_key": "acct-active",
                "last_usage": {
                    "primary": {"used_percent": 12, "resets_at": 4_000},
                },
            },
        ],
    }))
    err = HTTPError(
        url="https://chatgpt.com/backend-api/wham/usage",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )

    with patch("quota_monitor.probes.codex.urlopen", side_effect=err):
        result = scan_codex(auth_file=auth, now=1_000.0)

    assert result.source == "codex"
    assert result.extra == {
        "used_percent": 12,
        "reset_at": 4_000,
        "fetched": False,
        "source": "codex-auth",
    }


def test_uses_last_hint_when_usage_api_fails_and_codex_auth_cache_unavailable(tmp_path):
    auth = tmp_path / "auth.json"
    auth.write_text('{"tokens": {"access_token": "expired"}}')
    hint = FetchHint(last_fetch_at=0, last_used_percent=23, last_reset_at=4_000)
    err = HTTPError(
        url="https://chatgpt.com/backend-api/wham/usage",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )

    with patch("quota_monitor.probes.codex.urlopen", side_effect=err):
        result = scan_codex(auth_file=auth, now=1_000.0, hint=hint)

    assert result.extra == {
        "used_percent": 23,
        "reset_at": 4_000,
        "fetched": False,
        "source": "last-success",
    }


def test_returns_unavailable_when_usage_api_fails_without_cache(tmp_path):
    auth = tmp_path / "auth.json"
    auth.write_text('{"tokens": {"access_token": "expired"}}')
    err = HTTPError(
        url="https://chatgpt.com/backend-api/wham/usage",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )

    with patch("quota_monitor.probes.codex.urlopen", side_effect=err):
        result = scan_codex(auth_file=auth, now=1_000.0)

    assert result.extra == {
        "used_percent": 0,
        "reset_at": None,
        "fetched": False,
        "source": "unavailable",
    }
