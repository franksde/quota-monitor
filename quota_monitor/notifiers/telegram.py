import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .. import __version__
from . import Alert, NotifierError


class TelegramNotifier:
    name = "telegram"

    def __init__(self, *, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, alert: Alert) -> None:
        if not self.bot_token or not self.chat_id:
            raise NotifierError("telegram credentials missing", retryable=False)
        text = f"*{alert.title}*\n\n{alert.body}"
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = json.dumps({"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}).encode()
        req = Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "User-Agent": f"QuotaMonitor/{__version__}",
        })
        try:
            with urlopen(req, timeout=10) as resp:
                if resp.status >= 400:
                    raise NotifierError(f"telegram returned {resp.status}", retryable=resp.status >= 500)
        except HTTPError as e:
            raise NotifierError(f"telegram HTTP {e.code}", retryable=e.code >= 500) from e
        except URLError as e:
            raise NotifierError(f"telegram network error: {e}", retryable=True) from e
