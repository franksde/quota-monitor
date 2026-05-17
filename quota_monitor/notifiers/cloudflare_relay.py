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
        body = {
            "reset_time_epoch": int(alert.reset_at),
            "message": f"*{alert.title}*\n\n{alert.body}",
        }
        # schedule_id is optional. When present the worker writes a tombstone
        # to KV so a later schedule for the same id will supersede this one
        # at delivery time. Old worker deployments (no KV) ignore the field.
        if alert.schedule_id:
            body["schedule_id"] = alert.schedule_id
        payload = json.dumps(body).encode()
        req = Request(self.webhook_url, data=payload, headers={
            "Content-Type": "application/json",
            "User-Agent": "QuotaMonitor/0.1.0",
        })
        try:
            with urlopen(req, timeout=10) as resp:
                if resp.status >= 400:
                    raise NotifierError(f"relay returned {resp.status}", retryable=resp.status >= 500)
        except HTTPError as e:
            raise NotifierError(f"relay HTTP {e.code}", retryable=e.code >= 500) from e
        except URLError as e:
            raise NotifierError(f"relay network error: {e}", retryable=True) from e
