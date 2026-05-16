from unittest.mock import patch, MagicMock
import pytest
from urllib.error import URLError, HTTPError
from quota_monitor.notifiers import Alert, NotifierError
from quota_monitor.notifiers.telegram import TelegramNotifier


def _fake_response(status: int = 200, body: bytes = b'{"ok":true}'):
    fake = MagicMock()
    fake.status = status
    fake.read.return_value = body
    fake.__enter__ = lambda self: fake
    fake.__exit__ = lambda self, *a: None
    return fake


def test_send_posts_to_bot_api():
    notifier = TelegramNotifier(bot_token="TOK", chat_id="CID")
    with patch("quota_monitor.notifiers.telegram.urlopen", return_value=_fake_response()) as op:
        notifier.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    call = op.call_args[0][0]
    assert "api.telegram.org/botTOK/sendMessage" in call.full_url


def test_send_raises_retryable_on_url_error():
    notifier = TelegramNotifier(bot_token="TOK", chat_id="CID")
    with patch("quota_monitor.notifiers.telegram.urlopen", side_effect=URLError("nope")):
        with pytest.raises(NotifierError) as exc:
            notifier.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    assert exc.value.retryable is True


def test_send_raises_non_retryable_on_4xx():
    notifier = TelegramNotifier(bot_token="TOK", chat_id="CID")
    err = HTTPError(url="x", code=401, msg="Unauthorized", hdrs=None, fp=None)
    with patch("quota_monitor.notifiers.telegram.urlopen", side_effect=err):
        with pytest.raises(NotifierError) as exc:
            notifier.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    assert exc.value.retryable is False


def test_send_raises_retryable_on_5xx():
    notifier = TelegramNotifier(bot_token="TOK", chat_id="CID")
    err = HTTPError(url="x", code=503, msg="Bad", hdrs=None, fp=None)
    with patch("quota_monitor.notifiers.telegram.urlopen", side_effect=err):
        with pytest.raises(NotifierError) as exc:
            notifier.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    assert exc.value.retryable is True


def test_missing_token_or_chat_id_raises_non_retryable_immediately():
    n = TelegramNotifier(bot_token="", chat_id="cid")
    with pytest.raises(NotifierError) as exc:
        n.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    assert exc.value.retryable is False
