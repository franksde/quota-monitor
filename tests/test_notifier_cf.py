from unittest.mock import patch, MagicMock
import pytest
from urllib.error import URLError, HTTPError
from quota_monitor.notifiers import Alert, NotifierError
from quota_monitor.notifiers.cloudflare_relay import CloudflareRelayNotifier


def _fake_response(status: int = 200):
    fake = MagicMock()
    fake.status = status
    fake.__enter__ = lambda self: fake
    fake.__exit__ = lambda self, *a: None
    return fake


def test_send_posts_reset_time_and_message():
    n = CloudflareRelayNotifier(webhook_url="https://relay.example.com/api/schedule")
    with patch("quota_monitor.notifiers.cloudflare_relay.urlopen", return_value=_fake_response()) as op:
        n.send(Alert(title="T", body="B", reset_at=999, source="claude"))
    req = op.call_args[0][0]
    assert req.full_url == "https://relay.example.com/api/schedule"
    body = req.data
    assert b'"reset_time_epoch": 999' in body or b'"reset_time_epoch":999' in body


def test_send_raises_non_retryable_when_webhook_url_empty():
    n = CloudflareRelayNotifier(webhook_url="")
    with pytest.raises(NotifierError) as exc:
        n.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    assert exc.value.retryable is False


def test_network_error_is_retryable():
    n = CloudflareRelayNotifier(webhook_url="https://x.example/api")
    with patch("quota_monitor.notifiers.cloudflare_relay.urlopen", side_effect=URLError("nope")):
        with pytest.raises(NotifierError) as exc:
            n.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    assert exc.value.retryable is True


def test_5xx_is_retryable():
    err = HTTPError(url="x", code=502, msg="Bad", hdrs=None, fp=None)
    n = CloudflareRelayNotifier(webhook_url="https://x.example/api")
    with patch("quota_monitor.notifiers.cloudflare_relay.urlopen", side_effect=err):
        with pytest.raises(NotifierError) as exc:
            n.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    assert exc.value.retryable is True
