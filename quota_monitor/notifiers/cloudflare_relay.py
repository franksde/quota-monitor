import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import Alert, NotifierError


class CloudflareRelayNotifier:
    name = "cloudflare_relay"

    def __init__(self, *, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, alert: Alert) -> None:
        if not self.webhook_url:
            raise NotifierError("cloudflare_relay webhook_url not configured", retryable=False)
        payload = json.dumps({
            "reset_time_epoch": int(alert.reset_at),
            "message": f"*{alert.title}*\n\n{alert.body}",
        }).encode()
        req = Request(self.webhook_url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as resp:
                if resp.status >= 400:
                    raise NotifierError(f"relay returned {resp.status}", retryable=resp.status >= 500)
        except HTTPError as e:
            raise NotifierError(f"relay HTTP {e.code}", retryable=e.code >= 500) from e
        except URLError as e:
            raise NotifierError(f"relay network error: {e}", retryable=True) from e
