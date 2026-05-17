# Adding a HUD adapter

QuotaMonitor reads precise 5h / 7d quota data from a priority chain of
sources (see `quota_monitor/probes/precise.py::read_precise`):

1. **Our own statusline wrapper cache** — fastest path for users where
   Claude Code's statusline payload carries fresh `rate_limits` headers
   (Anthropic-direct usage).
2. **HUD-tool caches** — third-party statusline tools like `claude-hud`
   or `oh-my-claude` already query Anthropic's `/api/oauth/usage` and
   cache the result locally. We piggyback on those caches instead of
   re-implementing the OAuth dance.
3. **Replay-window estimate** — last-resort heuristic from local jsonl
   timestamps. Inherently imprecise; see README.

If you run a HUD that's not yet supported, this guide shows how to add
the adapter. Self-contained, ~50 lines + tests.

## Currently supported HUDs

| Adapter | Cache file | Schema |
|---|---|---|
| `claude-hud` | `~/.claude/plugins/claude-hud/.usage-cache.json` | `{data: {fiveHour, sevenDay, fiveHourResetAt (ISO), sevenDayResetAt (ISO)}, timestamp (ms)}` |
| `oh-my-claude` | `~/.claude/plugins/oh-my-claudecode/.usage-cache-anthropic.json` | `{data: {fiveHourPercent, weeklyPercent, fiveHourResetsAt (ISO), weeklyResetsAt (ISO)}, timestamp (ms)}` |

## Adding a new adapter

1. **Find the cache file**. On a machine that runs the HUD, look in
   `~/.claude/plugins/<tool>/` for a file named `*usage*` or `*cache*`.
   Most tools follow the convention `(.usage|usage)-cache(-source).json`.

2. **Confirm the schema**. Open the file and identify the four fields
   we need (5h pct, 5h reset, 7d pct, 7d reset) plus a timestamp.
   Note the exact key names — they vary (`fiveHour` vs `fiveHourPercent`,
   `fiveHourResetAt` vs `fiveHourResetsAt`).

3. **Implement the reader** in `quota_monitor/probes/hud_adapters.py`:

   ```python
   def read_<your_hud>(now: float, *, home: Optional[Path] = None) -> Optional[HudUsageData]:
       """One-line description."""
       home = home or Path.home()
       cache_path = home / ".claude" / "plugins" / "<tool-dir>" / "<cache-file>.json"
       if not cache_path.exists():
           return None
       try:
           raw = json.loads(cache_path.read_text())
       except (json.JSONDecodeError, OSError):
           return None

       timestamp_ms = raw.get("timestamp")
       if not isinstance(timestamp_ms, (int, float)) or timestamp_ms <= 0:
           return None
       captured_at = float(timestamp_ms) / 1000.0

       data = raw.get("data") or {}
       five_hour_pct = data.get("<5h-pct-key>")
       seven_day_pct = data.get("<7d-pct-key>")
       if not isinstance(five_hour_pct, (int, float)) or not isinstance(seven_day_pct, (int, float)):
           return None

       five_hour_resets_at = _parse_iso8601_to_epoch(data.get("<5h-reset-key>"))
       seven_day_resets_at = _parse_iso8601_to_epoch(data.get("<7d-reset-key>"))
       if five_hour_resets_at is None or seven_day_resets_at is None:
           return None

       # Standard freshness gate — let stale-but-recent (within grace) caches through.
       if five_hour_resets_at < now - RESET_GRACE_SECONDS:
           return None

       return HudUsageData(
           five_hour_pct=float(five_hour_pct),
           five_hour_resets_at=five_hour_resets_at,
           seven_day_pct=float(seven_day_pct),
           seven_day_resets_at=seven_day_resets_at,
           captured_at=captured_at,
           source="<your-hud-name>",
       )
   ```

4. **Wire into the priority chain** in `quota_monitor/probes/precise.py`:

   ```python
   from .hud_adapters import RESET_GRACE_SECONDS, read_claude_hud, read_oh_my_claude, read_<your_hud>
   # ...
   for hud_reader in (read_claude_hud, read_oh_my_claude, read_<your_hud>):
       hud = hud_reader(now)
       if hud is not None:
           return PreciseUsage(...)
   ```

   **Order matters**. Earlier entries win when both are fresh. Pick a
   position based on how widely the HUD is deployed; new community
   adapters at the end.

5. **Add tests** in `tests/test_hud_adapters.py` covering at minimum:
   happy path, missing file, malformed JSON, missing fields,
   reset-past-grace. Copy the `_write_omc_cache` / `_write_claude_hud_cache`
   helpers as a template.

6. **Update the table at the top of this doc** with your adapter.

7. Run `.venv/bin/pytest tests/test_hud_adapters.py tests/test_precise_probe.py -v`.

## Why the freshness rule is "reset in future OR within RESET_GRACE_SECONDS past"

All HUD caches are *passive* — they only refresh when the user is active in
Claude Code. The user is typically idle around reset time (they've burned
the window and are waiting). Without the grace, every reset event creates
a dead window of up to 5-30 minutes where precise data is unreachable
exactly when our "recovered" notification needs it.

The reset *value* in the cache is a hard fact and doesn't decay. Usage
pct may be stale by a few points; worst case is a one-tick alert delay,
which is acceptable.
