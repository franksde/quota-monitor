# Linux systemd Timer

Linux support is best-effort. Use a user-level systemd timer.

```ini
# ~/.config/systemd/user/quota-monitor.timer
[Unit]
Description=QuotaMonitor periodic scan

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Unit=quota-monitor.service

[Install]
WantedBy=timers.target
```

```ini
# ~/.config/systemd/user/quota-monitor.service
[Unit]
Description=QuotaMonitor single scan

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -m quota_monitor run
StandardOutput=append:%h/.quota-monitor/quota-monitor.log
StandardError=append:%h/.quota-monitor/quota-monitor.err.log
```

Enable it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now quota-monitor.timer
systemctl --user list-timers quota-monitor.timer
```
