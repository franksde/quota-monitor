# QuotaMonitor Open-Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a zero-dependency, AI-Agent-friendly, open-source rewrite of QuotaMonitor that monitors Claude / Codex 5h quota windows and notifies via configurable backends, with an opt-in keepalive feature.

**Architecture:** Python 3.11+, stdlib-only runtime. Modules: `probes/` (data extraction) → `core/` (window state, decision, dispatch) → `notifiers/` (Telegram / macOS native / CF relay). Opt-in `keepalive/` (polling / seamless strategies + phrase pool). Config = TOML + `.env`. State = `~/.quota-monitor/state.json` (atomic write). CLI = `setup` (interactive wizard with preflight) + `run` (cron entry) + auxiliary commands.

**Tech Stack:** Python 3.11+ (stdlib `tomllib`, `argparse`, `unittest.mock`), pytest, Cloudflare Workers (JS) for optional relay, `wrangler` CLI for deploy.

**Spec reference:** `docs/superpowers/specs/2026-05-16-open-source-design.md`

---

## Conventions

- **Working directory** for all commands: `/Users/frank/Documents/Frank/OpenClaw/quota-monitor/` (the new repo, already `git init -b main`).
- **Python interpreter**: `python3.11` or higher. Run `python3 --version` to confirm.
- **Test runner**: `pytest`. Install once: `python3 -m pip install --user pytest` (the only dev dependency).
- **Commit messages**: Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`).
- **Per-task commit**: every task ends with one commit. Don't squash.

---

## Task Map (32 tasks)

| # | Task | Layer |
|---|---|---|
| T1  | Repo skeleton + pyproject + pytest smoke | foundation |
| T2  | `config/dotenv.py` self-written KV parser | foundation |
| T3  | `config/schema.py` + `config/loader.py` (TOML + .env merge) | foundation |
| T4  | `core/state.py` atomic IO + self-heal | foundation |
| T5  | `probes/__init__.py` ProbeResult dataclass | probes |
| T6  | `probes/claude.py` + fixtures | probes |
| T7  | `probes/codex.py` + fixtures | probes |
| T8  | `platform/paths.py` | platform |
| T9  | `core/window.py` algorithm + decision | core |
| T10 | `notifiers/__init__.py` Protocol + Alert | notifiers |
| T11 | `notifiers/telegram.py` | notifiers |
| T12 | `notifiers/macos_native.py` | notifiers |
| T13 | `notifiers/cloudflare_relay.py` | notifiers |
| T14 | `core/dispatch.py` retry + fallback | core |
| T15 | `i18n/` t() + en/zh messages | i18n |
| T16 | `keepalive/phrases.py` no-repeat sampling | keepalive |
| T17 | `keepalive/activity.py` + `keepalive/runner.py` | keepalive |
| T18 | `keepalive/polling.py` | keepalive |
| T19 | `keepalive/seamless.py` (port original tmux) | keepalive |
| T20 | `platform/schedule.py` LaunchAgent plist | platform |
| T21 | `cli/run.py` main flow + integration test | cli |
| T22 | `cli/status.py` | cli |
| T23 | `cli/notify_test.py` | cli |
| T24 | `cli/uninstall.py` | cli |
| T25 | `cli/setup.py` wizard (preflight + steps 1-4, 6, 7) | cli |
| T26 | `cli/setup.py` step 5 CF integration | cli |
| T27 | `cloudflare-relay/` rebuild | cf |
| T28 | `README.md` English | docs |
| T29 | `README.zh-CN.md` Chinese | docs |
| T30 | `docs/` subdocs (ARCHITECTURE / cloudflare / adding-notifier / linux-systemd) | docs |
| T31 | `config.example.toml` / `.env.example` / `LICENSE` / `CONTRIBUTING.md` | meta |
| T32 | Run v1 acceptance checklist from spec §14 | release |

---

## Task 1: Repo skeleton + pyproject + pytest smoke

**Files:**
- Create: `pyproject.toml`
- Create: `quota_monitor/__init__.py`
- Create: `quota_monitor/__main__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_smoke.py`

- [ ] **Step 1: Write the smoke test**

`tests/test_smoke.py`:
```python
def test_package_imports():
    import quota_monitor
    assert quota_monitor.__version__

def test_module_runnable():
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "quota_monitor", "--help"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "quota_monitor" in result.stdout.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/test_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quota_monitor'`

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "quota-monitor"
version = "0.1.0"
description = "Monitor Claude / Codex 5-hour quota windows and notify on reset."
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [{name = "Frank"}]
dependencies = []  # zero runtime dependencies

[project.optional-dependencies]
dev = ["pytest>=7"]

[project.scripts]
quota-monitor = "quota_monitor.__main__:main"

[tool.setuptools.packages.find]
include = ["quota_monitor*"]
exclude = ["tests*"]
```

- [ ] **Step 4: Write `quota_monitor/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Write `quota_monitor/__main__.py`**

```python
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quota_monitor",
        description="Monitor Claude / Codex 5-hour quota windows.",
    )
    parser.add_argument("--version", action="version", version="quota_monitor 0.1.0")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("setup", help="interactive setup wizard")
    sub.add_parser("run", help="single scan (cron entry)")
    sub.add_parser("status", help="show current state")
    sub.add_parser("notify-test", help="send a test notification")
    sub.add_parser("uninstall", help="remove LaunchAgent")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    # subcommand handlers wired in later tasks
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Write `tests/__init__.py` and `tests/conftest.py`**

`tests/__init__.py`: empty file.

`tests/conftest.py`:
```python
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `import quota_monitor` works without install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `python3 -m pytest tests/test_smoke.py -v`
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml quota_monitor/ tests/
git commit -m "feat: repo skeleton with pyproject and pytest smoke"
```

---

## Task 2: `config/dotenv.py` self-written KV parser

**Files:**
- Create: `quota_monitor/config/__init__.py`
- Create: `quota_monitor/config/dotenv.py`
- Test: `tests/test_dotenv.py`

- [ ] **Step 1: Write failing tests**

`tests/test_dotenv.py`:
```python
import pytest
from quota_monitor.config.dotenv import parse_dotenv


def test_parses_simple_kv():
    assert parse_dotenv("FOO=bar\nBAZ=qux") == {"FOO": "bar", "BAZ": "qux"}

def test_skips_comments_and_blanks():
    text = """
    # a comment
    FOO=bar

    # another
    BAZ=qux
    """
    assert parse_dotenv(text) == {"FOO": "bar", "BAZ": "qux"}

def test_strips_inline_whitespace():
    assert parse_dotenv("  FOO = bar  ") == {"FOO": "bar"}

def test_handles_quoted_values():
    assert parse_dotenv('FOO="bar baz"') == {"FOO": "bar baz"}
    assert parse_dotenv("FOO='bar baz'") == {"FOO": "bar baz"}

def test_handles_empty_value():
    assert parse_dotenv("FOO=") == {"FOO": ""}

def test_ignores_malformed_lines():
    assert parse_dotenv("not_a_kv\nFOO=bar") == {"FOO": "bar"}

def test_returns_empty_dict_for_empty_input():
    assert parse_dotenv("") == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_dotenv.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quota_monitor.config'`.

- [ ] **Step 3: Write `quota_monitor/config/__init__.py`**

Empty file.

- [ ] **Step 4: Write `quota_monitor/config/dotenv.py`**

```python
"""Minimal `.env` KV parser. No third-party dependency."""


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse a `.env`-style string into a dict.

    Supports: comments (#), blank lines, quoted values ('' or ""),
    surrounding whitespace. Malformed lines are silently skipped.
    """
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if not key:
            continue
        result[key] = value
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_dotenv.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/config/ tests/test_dotenv.py
git commit -m "feat(config): minimal .env KV parser with quote and comment support"
```

---

## Task 3: `config/schema.py` + `config/loader.py` (TOML + .env merge)

**Files:**
- Create: `quota_monitor/config/schema.py`
- Create: `quota_monitor/config/loader.py`
- Test: `tests/test_config.py`
- Test fixtures: `tests/fixtures/config/valid.toml`, `tests/fixtures/config/missing_primary.toml`

- [ ] **Step 1: Write failing tests**

`tests/fixtures/config/valid.toml`:
```toml
locale = "en"
log_level = "info"

[probes.claude]
enabled = true
threshold_turns = 5
window_hours = 5

[probes.codex]
enabled = false
threshold_percent = 30

[notifiers]
primary = "telegram"
fallback = "macos_native"

[notifiers.telegram]

[notifiers.cloudflare_relay]
enabled = false
webhook_url = ""

[keepalive]
enabled = false
strategy = "polling"
model = "haiku"
phrase_pool = []
seamless_trigger_minutes = 30
seamless_buffer_seconds = 60
```

`tests/fixtures/config/missing_primary.toml` — same as above but with `primary = ""` instead of `"telegram"`.

`tests/test_config.py`:
```python
from pathlib import Path
import pytest
from quota_monitor.config.loader import load_config, ConfigError

FIXTURES = Path(__file__).parent / "fixtures" / "config"


def test_loads_valid_config(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=cid\n")
    cfg = load_config(FIXTURES / "valid.toml", env)
    assert cfg.locale == "en"
    assert cfg.probes.claude.enabled is True
    assert cfg.probes.claude.threshold_turns == 5
    assert cfg.probes.codex.enabled is False
    assert cfg.notifiers.primary == "telegram"
    assert cfg.notifiers.fallback == "macos_native"
    assert cfg.keepalive.enabled is False
    assert cfg.keepalive.strategy == "polling"
    assert cfg.secrets["TELEGRAM_BOT_TOKEN"] == "tok"
    assert cfg.secrets["TELEGRAM_CHAT_ID"] == "cid"


def test_rejects_empty_primary_notifier():
    with pytest.raises(ConfigError, match="primary"):
        load_config(FIXTURES / "missing_primary.toml", env_path=None)


def test_missing_config_file_raises_clearly(tmp_path):
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(tmp_path / "nope.toml", env_path=None)


def test_invalid_strategy_rejected(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        '[notifiers]\nprimary="telegram"\n[keepalive]\nstrategy="wat"\n'
    )
    with pytest.raises(ConfigError, match="strategy"):
        load_config(bad, env_path=None)


def test_missing_env_file_is_ok(tmp_path):
    cfg = load_config(FIXTURES / "valid.toml", env_path=tmp_path / "no.env")
    assert cfg.secrets == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: FAIL with import errors.

- [ ] **Step 3: Write `quota_monitor/config/schema.py`**

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClaudeProbeConfig:
    enabled: bool = True
    threshold_turns: int = 5
    window_hours: int = 5


@dataclass(frozen=True)
class CodexProbeConfig:
    enabled: bool = True
    threshold_percent: int = 30


@dataclass(frozen=True)
class ProbesConfig:
    claude: ClaudeProbeConfig = field(default_factory=ClaudeProbeConfig)
    codex: CodexProbeConfig = field(default_factory=CodexProbeConfig)


@dataclass(frozen=True)
class CloudflareRelayConfig:
    enabled: bool = False
    webhook_url: str = ""


@dataclass(frozen=True)
class NotifiersConfig:
    primary: str = "telegram"
    fallback: str = "macos_native"
    cloudflare_relay: CloudflareRelayConfig = field(default_factory=CloudflareRelayConfig)


@dataclass(frozen=True)
class KeepaliveConfig:
    enabled: bool = False
    strategy: str = "polling"  # "polling" | "seamless"
    model: str = "haiku"
    phrase_pool: tuple[str, ...] = ()
    seamless_trigger_minutes: int = 30
    seamless_buffer_seconds: int = 60


@dataclass(frozen=True)
class Config:
    locale: str = "en"
    log_level: str = "info"
    probes: ProbesConfig = field(default_factory=ProbesConfig)
    notifiers: NotifiersConfig = field(default_factory=NotifiersConfig)
    keepalive: KeepaliveConfig = field(default_factory=KeepaliveConfig)
    secrets: dict[str, str] = field(default_factory=dict)


VALID_STRATEGIES = ("polling", "seamless")
VALID_LOCALES = ("en", "zh")
```

- [ ] **Step 4: Write `quota_monitor/config/loader.py`**

```python
import tomllib
from pathlib import Path

from .dotenv import parse_dotenv
from .schema import (
    ClaudeProbeConfig,
    CloudflareRelayConfig,
    CodexProbeConfig,
    Config,
    KeepaliveConfig,
    NotifiersConfig,
    ProbesConfig,
    VALID_LOCALES,
    VALID_STRATEGIES,
)


class ConfigError(Exception):
    """Raised when configuration is invalid or unreadable."""


def load_config(toml_path: Path, env_path: Path | None) -> Config:
    if not toml_path.exists():
        raise ConfigError(f"config file not found: {toml_path}. Run `quota-monitor setup`.")

    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"config file is not valid TOML: {e}")

    locale = data.get("locale", "en")
    if locale not in VALID_LOCALES:
        raise ConfigError(f"locale must be one of {VALID_LOCALES}, got {locale!r}")

    probes_block = data.get("probes", {})
    probes = ProbesConfig(
        claude=ClaudeProbeConfig(**(probes_block.get("claude") or {})),
        codex=CodexProbeConfig(**(probes_block.get("codex") or {})),
    )

    notifiers_block = data.get("notifiers", {})
    primary = notifiers_block.get("primary", "")
    if not primary:
        raise ConfigError("notifiers.primary must not be empty")
    cf = CloudflareRelayConfig(**(notifiers_block.get("cloudflare_relay") or {}))
    notifiers = NotifiersConfig(
        primary=primary,
        fallback=notifiers_block.get("fallback", ""),
        cloudflare_relay=cf,
    )

    ka_block = data.get("keepalive", {}) or {}
    if "phrase_pool" in ka_block:
        ka_block = {**ka_block, "phrase_pool": tuple(ka_block["phrase_pool"])}
    keepalive = KeepaliveConfig(**ka_block)
    if keepalive.strategy not in VALID_STRATEGIES:
        raise ConfigError(
            f"keepalive.strategy must be one of {VALID_STRATEGIES}, got {keepalive.strategy!r}"
        )

    secrets: dict[str, str] = {}
    if env_path is not None and env_path.exists():
        secrets = parse_dotenv(env_path.read_text())

    return Config(
        locale=locale,
        log_level=data.get("log_level", "info"),
        probes=probes,
        notifiers=notifiers,
        keepalive=keepalive,
        secrets=secrets,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/config/ tests/test_config.py tests/fixtures/config/
git commit -m "feat(config): TOML + .env loader with frozen dataclass schema"
```

---

## Task 4: `core/state.py` atomic IO + self-heal

> **Design note (post-bug-fix):** State JSON is **deliberately minimal**. It records ONLY "has this reset point already been alerted?" — never participates in window-slicing. The original QuotaMonitor had a bug where saving `current_window_reset` and using it to filter probe timestamps silenced alerts whenever the saved reset was in the future. The Full Replay algorithm in Task 9 takes no state as input, so `ClaudeState` only needs `alerted_for_reset`.

**Files:**
- Create: `quota_monitor/core/__init__.py`
- Create: `quota_monitor/core/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing tests**

`tests/test_state.py`:
```python
import json
from dataclasses import replace
from pathlib import Path
import pytest
from quota_monitor.core.state import State, ClaudeState, load_state, save_state, default_state


def test_default_state_has_schema_version():
    s = default_state()
    assert s.schema_version == 1
    assert s.claude.alerted_for_reset == 0
    assert s.codex.alerted_for_reset == 0
    assert s.keepalive.phrase_pool_used_indices == ()


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    s = replace(default_state(), claude=ClaudeState(alerted_for_reset=1000 + 5 * 3600))
    save_state(path, s)
    loaded = load_state(path)
    assert loaded.claude.alerted_for_reset == 1000 + 5 * 3600


def test_load_missing_file_returns_default(tmp_path):
    s = load_state(tmp_path / "no.json")
    assert s == default_state()


def test_load_corrupted_file_returns_default(tmp_path, capsys):
    path = tmp_path / "state.json"
    path.write_text("{not json")
    s = load_state(path)
    assert s == default_state()
    err = capsys.readouterr().err
    assert "corrupted" in err.lower() or "warn" in err.lower()


def test_atomic_write_no_partial_state(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    save_state(path, default_state())
    original = path.read_text()
    # Simulate failure during write: monkeypatch os.replace to raise after tmp written.
    import quota_monitor.core.state as state_mod

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(state_mod.os, "replace", boom)
    with pytest.raises(OSError):
        s = replace(default_state(), claude=ClaudeState(alerted_for_reset=999))
        save_state(path, s)
    # Original file unchanged.
    assert path.read_text() == original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_state.py -v`
Expected: FAIL with import errors.

- [ ] **Step 3: Write `quota_monitor/core/__init__.py`**

Empty file.

- [ ] **Step 4: Write `quota_monitor/core/state.py`**

```python
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ClaudeState:
    """Minimal: only tracks which reset point has already been alerted.
    Never stores window start/reset — those come from Full Replay each tick.
    """
    alerted_for_reset: int = 0


@dataclass(frozen=True)
class CodexState:
    alerted_for_reset: int = 0
    cooldown_until: int = 0


@dataclass(frozen=True)
class KeepaliveState:
    last_seamless_scheduled_for: int = 0
    phrase_pool_used_indices: tuple[int, ...] = ()
    phrase_pool_size_at_init: int = 0


@dataclass(frozen=True)
class State:
    schema_version: int = SCHEMA_VERSION
    claude: ClaudeState = field(default_factory=ClaudeState)
    codex: CodexState = field(default_factory=CodexState)
    keepalive: KeepaliveState = field(default_factory=KeepaliveState)


def default_state() -> State:
    return State()


def load_state(path: Path) -> State:
    if not path.exists():
        return default_state()
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"[warn] state file corrupted ({e}); resetting to defaults", file=sys.stderr)
        return default_state()

    try:
        # Backward-compatibility: silently ignore obsolete ClaudeState fields
        # (current_window_start / current_window_reset) that may exist in older state files.
        claude_block = {k: v for k, v in (raw.get("claude") or {}).items() if k in {"alerted_for_reset"}}
        return State(
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            claude=ClaudeState(**claude_block),
            codex=CodexState(**(raw.get("codex") or {})),
            keepalive=KeepaliveState(
                last_seamless_scheduled_for=(raw.get("keepalive") or {}).get("last_seamless_scheduled_for", 0),
                phrase_pool_used_indices=tuple((raw.get("keepalive") or {}).get("phrase_pool_used_indices", [])),
                phrase_pool_size_at_init=(raw.get("keepalive") or {}).get("phrase_pool_size_at_init", 0),
            ),
        )
    except TypeError as e:
        print(f"[warn] state schema mismatch ({e}); resetting to defaults", file=sys.stderr)
        return default_state()


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = asdict(state)
    # Convert tuples (json doesn't preserve type but lists are fine on load).
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_state.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/core/ tests/test_state.py
git commit -m "feat(core): state atomic IO with self-heal on corruption"
```

---

## Task 5: `probes/__init__.py` ProbeResult dataclass

**Files:**
- Create: `quota_monitor/probes/__init__.py`
- Test: `tests/test_probes_init.py`

- [ ] **Step 1: Write failing test**

`tests/test_probes_init.py`:
```python
from quota_monitor.probes import ProbeResult


def test_probe_result_carries_source_and_timestamps():
    r = ProbeResult(source="claude", timestamps=(1.0, 2.0, 3.0))
    assert r.source == "claude"
    assert r.timestamps == (1.0, 2.0, 3.0)
    assert r.extra == {}


def test_probe_result_extra_is_dict():
    r = ProbeResult(source="codex", timestamps=(), extra={"reset_at": 999})
    assert r.extra["reset_at"] == 999


def test_probe_result_is_immutable():
    import dataclasses
    r = ProbeResult(source="claude", timestamps=())
    try:
        r.source = "codex"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("ProbeResult should be frozen")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_probes_init.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/probes/__init__.py`**

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProbeResult:
    """Output of a probe scan. Pure data; no decisions."""
    source: str                                  # "claude" | "codex"
    timestamps: tuple[float, ...]                # epoch seconds, sorted ascending
    extra: dict[str, object] = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_probes_init.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/probes/ tests/test_probes_init.py
git commit -m "feat(probes): ProbeResult frozen dataclass"
```

---

## Task 6: `probes/claude.py` + fixtures

**Files:**
- Create: `quota_monitor/probes/claude.py`
- Test: `tests/test_probes_claude.py`
- Test fixtures: `tests/fixtures/claude/app-cache/session1.json`, `tests/fixtures/claude/cli-jsonl/run1.jsonl`, `tests/fixtures/claude/costs.jsonl`

- [ ] **Step 1: Write failing tests**

`tests/fixtures/claude/app-cache/session1.json`:
```json
{"lastActivityAt": 1747200000000, "completedTurns": 3}
```

`tests/fixtures/claude/cli-jsonl/run1.jsonl`:
```jsonl
{"type":"message","message":{"role":"user"},"timestamp":"2026-05-15T12:00:00Z"}
{"type":"message","message":{"role":"assistant"},"timestamp":"2026-05-15T12:00:30Z"}
{"type":"message","message":{"role":"user"},"timestamp":"2026-05-15T12:05:00Z"}
```

`tests/fixtures/claude/costs.jsonl`:
```jsonl
{"timestamp":"2026-05-15T13:00:00Z","cost":0.001}
```

`tests/test_probes_claude.py`:
```python
from pathlib import Path
from quota_monitor.probes.claude import scan_claude

FIXTURES = Path(__file__).parent / "fixtures" / "claude"


def test_scans_app_cache(monkeypatch, tmp_path):
    result = scan_claude(
        app_dir=FIXTURES / "app-cache",
        cli_dir=tmp_path,
        costs_file=tmp_path / "nope.jsonl",
        now=1747200000.0 + 60,   # 1 minute after lastActivityAt
        window_seconds=5 * 3600,
    )
    assert result.source == "claude"
    assert 1747200000.0 in result.timestamps
    assert result.timestamps.count(1747200000.0) == 3   # 3 turns expanded


def test_scans_cli_jsonl_user_messages_only(monkeypatch, tmp_path):
    result = scan_claude(
        app_dir=tmp_path,
        cli_dir=FIXTURES / "cli-jsonl",
        costs_file=tmp_path / "nope.jsonl",
        now=1747312000.0,
        window_seconds=5 * 3600,
    )
    assert len(result.timestamps) == 2   # 2 user messages, assistant skipped


def test_skips_old_files(monkeypatch, tmp_path):
    # Use a very recent `now`; fixtures are from 2026-05 epochs, so they're outside the window.
    result = scan_claude(
        app_dir=FIXTURES / "app-cache",
        cli_dir=FIXTURES / "cli-jsonl",
        costs_file=FIXTURES / "costs.jsonl",
        now=9999999999.0,
        window_seconds=5 * 3600,
    )
    assert result.timestamps == ()


def test_returns_sorted_unique_timestamps(tmp_path):
    result = scan_claude(
        app_dir=FIXTURES / "app-cache",
        cli_dir=FIXTURES / "cli-jsonl",
        costs_file=FIXTURES / "costs.jsonl",
        now=1747400000.0,
        window_seconds=10 * 3600,
    )
    assert list(result.timestamps) == sorted(result.timestamps)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_probes_claude.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quota_monitor.probes.claude'`.

- [ ] **Step 3: Write `quota_monitor/probes/claude.py`**

```python
import glob
import json
import os
from datetime import datetime
from pathlib import Path

from . import ProbeResult


def _iso_to_epoch(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def scan_claude(*, app_dir: Path, cli_dir: Path, costs_file: Path, now: float, window_seconds: int) -> ProbeResult:
    window_start = now - window_seconds
    out: list[float] = []

    # 1. Mac App session caches.
    for fpath in glob.glob(str(app_dir / "**" / "*.json"), recursive=True):
        try:
            if os.path.getmtime(fpath) < window_start:
                continue
            with open(fpath) as f:
                data = json.load(f)
            last_active = data.get("lastActivityAt", 0) / 1000.0
            if last_active >= window_start:
                turns = data.get("completedTurns", 1)
                out.extend([last_active] * turns)
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue

    # 2. CLI jsonl (user messages only).
    for fpath in glob.glob(str(cli_dir / "**" / "*.jsonl"), recursive=True):
        try:
            if os.path.getmtime(fpath) < window_start:
                continue
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("type") != "message":
                        continue
                    if (rec.get("message") or {}).get("role") != "user":
                        continue
                    ts_str = rec.get("timestamp")
                    if not ts_str:
                        continue
                    try:
                        ts = _iso_to_epoch(ts_str)
                    except ValueError:
                        continue
                    if ts >= window_start:
                        out.append(ts)
        except OSError:
            continue

    # 3. costs.jsonl (extra time-source, last 20 lines).
    try:
        if costs_file.exists() and os.path.getmtime(costs_file) >= window_start:
            with open(costs_file, encoding="utf-8") as f:
                lines = f.readlines()[-20:]
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = rec.get("timestamp")
                if not ts_str:
                    continue
                try:
                    ts = _iso_to_epoch(ts_str)
                except ValueError:
                    continue
                if ts >= window_start:
                    out.append(ts)
    except OSError:
        pass

    out.sort()
    return ProbeResult(source="claude", timestamps=tuple(out))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_probes_claude.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/probes/claude.py tests/test_probes_claude.py tests/fixtures/claude/
git commit -m "feat(probes): claude probe scans app cache + cli jsonl + costs.jsonl"
```

---

## Task 7: `probes/codex.py` + fixtures

**Files:**
- Create: `quota_monitor/probes/codex.py`
- Test: `tests/test_probes_codex.py`
- Test fixture: `tests/fixtures/codex/auth.json`

- [ ] **Step 1: Write failing tests**

`tests/fixtures/codex/auth.json`:
```json
{"tokens": {"access_token": "TEST_ACCESS_TOKEN"}}
```

`tests/test_probes_codex.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_probes_codex.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/probes/codex.py`**

```python
import json
from pathlib import Path
from urllib.request import Request, urlopen

from . import ProbeResult

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"


class CodexAuthMissingError(Exception):
    """Raised when the Codex auth file is missing, malformed, or has no token."""


def scan_codex(*, auth_file: Path) -> ProbeResult:
    if not auth_file.exists():
        raise CodexAuthMissingError(f"{auth_file} not found")
    try:
        auth = json.loads(auth_file.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise CodexAuthMissingError(f"{auth_file} malformed: {e}") from e
    token = (auth.get("tokens") or {}).get("access_token")
    if not token:
        raise CodexAuthMissingError(f"{auth_file} has no access_token")

    req = Request(USAGE_URL, headers={"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    primary = (data.get("rate_limit") or {}).get("primary_window") or {}
    return ProbeResult(
        source="codex",
        timestamps=(),
        extra={
            "used_percent": primary.get("used_percent", 0),
            "reset_at": primary.get("reset_at"),
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_probes_codex.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/probes/codex.py tests/test_probes_codex.py tests/fixtures/codex/
git commit -m "feat(probes): codex probe calls /wham/usage and surfaces reset_at"
```

---

## Task 8: `platform/paths.py`

**Files:**
- Create: `quota_monitor/platform/__init__.py`
- Create: `quota_monitor/platform/paths.py`
- Test: `tests/test_platform_paths.py`

- [ ] **Step 1: Write failing tests**

`tests/test_platform_paths.py`:
```python
from pathlib import Path
from quota_monitor.platform.paths import (
    user_data_dir, config_file, env_file, state_file,
    claude_app_dir, claude_cli_dir, claude_costs_file, codex_auth_file,
    launch_agent_path,
)


def test_user_data_dir_under_home():
    assert user_data_dir() == Path.home() / ".quota-monitor"


def test_config_and_env_files_in_data_dir():
    assert config_file() == Path.home() / ".quota-monitor" / "config.toml"
    assert env_file() == Path.home() / ".quota-monitor" / ".env"


def test_state_file_in_data_dir():
    assert state_file() == Path.home() / ".quota-monitor" / "state.json"


def test_claude_paths_macos():
    assert claude_app_dir() == Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"
    assert claude_cli_dir() == Path.home() / ".claude"
    assert claude_costs_file() == Path.home() / ".claude" / "metrics" / "costs.jsonl"


def test_codex_auth_path():
    assert codex_auth_file() == Path.home() / ".codex" / "auth.json"


def test_launch_agent_path_uses_label():
    assert launch_agent_path("io.github.frank.quotamonitor") == \
        Path.home() / "Library" / "LaunchAgents" / "io.github.frank.quotamonitor.plist"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_platform_paths.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/platform/__init__.py`** — empty file.

- [ ] **Step 4: Write `quota_monitor/platform/paths.py`**

```python
"""Single source of truth for filesystem layout.

macOS-only assumptions live here. Linux support will branch on platform.system().
"""
from pathlib import Path


def user_data_dir() -> Path:
    return Path.home() / ".quota-monitor"


def config_file() -> Path:
    return user_data_dir() / "config.toml"


def env_file() -> Path:
    return user_data_dir() / ".env"


def state_file() -> Path:
    return user_data_dir() / "state.json"


def claude_app_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"


def claude_cli_dir() -> Path:
    return Path.home() / ".claude"


def claude_costs_file() -> Path:
    return claude_cli_dir() / "metrics" / "costs.jsonl"


def codex_auth_file() -> Path:
    return Path.home() / ".codex" / "auth.json"


def launch_agent_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_platform_paths.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/platform/ tests/test_platform_paths.py
git commit -m "feat(platform): centralize macOS filesystem layout"
```

---

## Task 9: `core/window.py` Full Replay algorithm + decision

> **Bug fixed in this task.** The original `monitor.py` had `calculate_window_state(timestamps, last_reset_time)` filtering history by `ts >= last_reset_time`. When the saved `last_reset_time` was a **future** timestamp (e.g. saved as 20:43 while now is 20:41 — possible because we save `start + 5h` proactively), every historical timestamp was `< last_reset_time`, the filter returned `count = 0`, and **the system silently stopped alerting**. Fix: **Full Replay** — never read state to slice history. Replay all timestamps left-to-right, opening a new 5h window every time `ts >= current_reset`. The latest window after replay is the answer. State JSON only records "was this reset already alerted?" — it never participates in counting.

**Files:**
- Create: `quota_monitor/core/window.py`
- Test: `tests/test_window.py`

- [ ] **Step 1: Write failing tests**

`tests/test_window.py`:
```python
from quota_monitor.core.state import State, ClaudeState, CodexState, default_state
from quota_monitor.core.window import (
    replay_windows, decide_alerts, AlertDecision, LatestWindow, WINDOW_SECONDS,
)
from quota_monitor.probes import ProbeResult


# --- replay_windows: pure, takes no state ---

def test_empty_returns_none():
    assert replay_windows(()) is None


def test_single_timestamp_opens_first_window():
    w = replay_windows((1000.0,))
    assert w == LatestWindow(start=1000.0, reset=1000.0 + WINDOW_SECONDS, count=1)


def test_clustered_timestamps_same_window():
    ts = (1000.0, 1001.0, 1002.0, 1003.0, 1004.0)
    w = replay_windows(ts)
    assert w.start == 1000.0
    assert w.reset == 1000.0 + WINDOW_SECONDS
    assert w.count == 5


def test_returns_latest_window_when_history_spans_multiple_windows():
    base = 1000.0
    second_start = base + WINDOW_SECONDS + 1.0
    ts = (base, second_start, second_start + 10, second_start + 20)
    w = replay_windows(ts)
    assert w.start == second_start
    assert w.reset == second_start + WINDOW_SECONDS
    assert w.count == 3


def test_replay_sorts_unordered_input():
    a = replay_windows((3.0, 1.0, 2.0))
    b = replay_windows((1.0, 2.0, 3.0))
    assert a == b


def test_three_consecutive_windows_returns_third():
    base = 1000.0
    w2 = base + WINDOW_SECONDS + 1
    w3 = w2 + WINDOW_SECONDS + 1
    ts = (base, w2, w3, w3 + 10, w3 + 20)
    w = replay_windows(ts)
    assert w.start == w3
    assert w.count == 3


# --- regression: the original future-reset bug ---

def test_regression_future_reset_in_state_does_not_silence_alerts():
    """Original bug scenario: state has alerted_for_reset = future timestamp.
    Under Full Replay, state never feeds back into counting, so the algorithm
    happily computes the real latest window and triggers an alert.
    """
    now = 1000.0
    future = now + 120
    state = State(claude=ClaudeState(alerted_for_reset=int(future)))
    ts = (now - 3600, now - 1800, now - 1200, now - 600, now - 60)
    w = replay_windows(ts)
    assert w is not None
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=now,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert len(decisions) == 1
    assert decisions[0].source == "claude"
    assert decisions[0].reset_at == int(w.reset)


# --- decide_alerts ---

def test_decide_emits_claude_alert_when_threshold_met():
    state = default_state()
    w = LatestWindow(start=1000.0, reset=1000.0 + WINDOW_SECONDS, count=5)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=1010.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert len(decisions) == 1
    assert decisions[0].source == "claude"
    assert decisions[0].reset_at == int(1000.0 + WINDOW_SECONDS)


def test_decide_skips_when_below_threshold():
    state = default_state()
    w = LatestWindow(start=1000.0, reset=1000.0 + WINDOW_SECONDS, count=3)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=1010.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert decisions == []


def test_decide_suppresses_repeat_for_same_window():
    state = State(claude=ClaudeState(alerted_for_reset=int(1000.0 + WINDOW_SECONDS)))
    w = LatestWindow(start=1000.0, reset=1000.0 + WINDOW_SECONDS, count=6)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=1010.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert decisions == []


def test_decide_skips_when_window_already_in_past():
    state = default_state()
    w = LatestWindow(start=1.0, reset=1.0 + WINDOW_SECONDS, count=6)
    decisions = decide_alerts(
        state=state, claude_window=w, codex=None, now=1.0 + WINDOW_SECONDS + 10,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert decisions == []


def test_decide_emits_codex_alert_when_over_threshold():
    state = default_state()
    codex = ProbeResult(source="codex", timestamps=(), extra={"used_percent": 60, "reset_at": 99999})
    decisions = decide_alerts(
        state=state, claude_window=None, codex=codex, now=1.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert len(decisions) == 1
    assert decisions[0].source == "codex"
    assert decisions[0].reset_at == 99999


def test_decide_suppresses_codex_within_cooldown():
    state = State(codex=CodexState(cooldown_until=999999))
    codex = ProbeResult(source="codex", timestamps=(), extra={"used_percent": 60, "reset_at": 99999})
    decisions = decide_alerts(
        state=state, claude_window=None, codex=codex, now=1.0,
        claude_threshold=5, codex_threshold_percent=30,
    )
    assert decisions == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_window.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/core/window.py`**

```python
from dataclasses import dataclass
from typing import Optional

from .state import State
from ..probes import ProbeResult

WINDOW_SECONDS = 5 * 3600


@dataclass(frozen=True)
class LatestWindow:
    start: float
    reset: float
    count: int


@dataclass(frozen=True)
class AlertDecision:
    source: str       # "claude" | "codex"
    reset_at: int     # epoch seconds


def replay_windows(timestamps: tuple[float, ...]) -> Optional[LatestWindow]:
    """Full Replay: scan all timestamps left-to-right, opening a new 5h window
    every time `ts >= current_reset`. Returns the LATEST window after replay,
    or None if there are no timestamps.

    State JSON intentionally does NOT feed in here. The original QuotaMonitor
    used a saved `last_reset_time` to filter history; when that saved value
    drifted into the future, every historical timestamp was filtered out and
    alerts silently stopped. Full Replay makes that failure mode structurally
    impossible.
    """
    if not timestamps:
        return None
    sorted_ts = sorted(timestamps)
    start = sorted_ts[0]
    reset = start + WINDOW_SECONDS
    count = 1
    for ts in sorted_ts[1:]:
        if ts >= reset:
            start = ts
            reset = ts + WINDOW_SECONDS
            count = 1
        else:
            count += 1
    return LatestWindow(start=start, reset=reset, count=count)


def decide_alerts(
    *,
    state: State,
    claude_window: Optional[LatestWindow],
    codex: Optional[ProbeResult],
    now: float,
    claude_threshold: int,
    codex_threshold_percent: int,
) -> list[AlertDecision]:
    decisions: list[AlertDecision] = []

    if claude_window is not None:
        if (
            claude_window.count >= claude_threshold
            and claude_window.reset > now
            and state.claude.alerted_for_reset != int(claude_window.reset)
        ):
            decisions.append(AlertDecision(source="claude", reset_at=int(claude_window.reset)))

    if codex is not None:
        used_percent = int(codex.extra.get("used_percent", 0) or 0)
        reset_at = codex.extra.get("reset_at")
        if (
            reset_at is not None
            and used_percent >= codex_threshold_percent
            and state.codex.cooldown_until <= now
            and state.codex.alerted_for_reset != int(reset_at)
        ):
            decisions.append(AlertDecision(source="codex", reset_at=int(reset_at)))

    return decisions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_window.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/core/window.py tests/test_window.py
git commit -m "feat(core): Full Replay window algorithm — stateless, regression-safe

State JSON no longer participates in window slicing. Fixes original
bug where a future-dated saved reset silenced all alerts."
```

---

## Task 10: `notifiers/__init__.py` Protocol + Alert

**Files:**
- Create: `quota_monitor/notifiers/__init__.py`
- Test: `tests/test_notifier_protocol.py`

- [ ] **Step 1: Write failing tests**

`tests/test_notifier_protocol.py`:
```python
from quota_monitor.notifiers import Alert, Notifier, NotifierError


def test_alert_dataclass_shape():
    a = Alert(title="t", body="b", reset_at=100, source="claude")
    assert a.title == "t"
    assert a.source == "claude"


def test_notifier_error_carries_retryable_flag():
    e = NotifierError("x", retryable=True)
    assert e.retryable is True
    e2 = NotifierError("x", retryable=False)
    assert e2.retryable is False


def test_dummy_notifier_implements_protocol():
    class Dummy:
        name = "dummy"
        def send(self, alert: Alert) -> None:
            return None

    n: Notifier = Dummy()
    n.send(Alert(title="t", body="b", reset_at=1, source="claude"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_notifier_protocol.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/notifiers/__init__.py`**

```python
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Alert:
    title: str        # i18n-resolved
    body: str         # i18n-resolved, may include markdown
    reset_at: int     # epoch seconds; relays use this to schedule delivery
    source: str       # "claude" | "codex"


class NotifierError(Exception):
    """Raised by Notifier.send on failure. `retryable=True` for transient (network) issues."""

    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


@runtime_checkable
class Notifier(Protocol):
    name: str

    def send(self, alert: Alert) -> None:
        """Send the alert. Return None on success, raise NotifierError on failure."""
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_notifier_protocol.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/notifiers/__init__.py tests/test_notifier_protocol.py
git commit -m "feat(notifiers): Notifier Protocol, Alert dataclass, NotifierError"
```

---

## Task 11: `notifiers/telegram.py`

**Files:**
- Create: `quota_monitor/notifiers/telegram.py`
- Test: `tests/test_notifier_telegram.py`

- [ ] **Step 1: Write failing tests**

`tests/test_notifier_telegram.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_notifier_telegram.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/notifiers/telegram.py`**

```python
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=10) as resp:
                if resp.status >= 400:
                    raise NotifierError(f"telegram returned {resp.status}", retryable=resp.status >= 500)
        except HTTPError as e:
            raise NotifierError(f"telegram HTTP {e.code}", retryable=e.code >= 500) from e
        except URLError as e:
            raise NotifierError(f"telegram network error: {e}", retryable=True) from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_notifier_telegram.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/notifiers/telegram.py tests/test_notifier_telegram.py
git commit -m "feat(notifiers): telegram bot API implementation with retry classification"
```

---

## Task 12: `notifiers/macos_native.py`

**Files:**
- Create: `quota_monitor/notifiers/macos_native.py`
- Test: `tests/test_notifier_macos.py`

- [ ] **Step 1: Write failing tests**

`tests/test_notifier_macos.py`:
```python
from unittest.mock import patch, MagicMock
import pytest
from quota_monitor.notifiers import Alert, NotifierError
from quota_monitor.notifiers.macos_native import MacOSNativeNotifier


def test_send_invokes_osascript():
    notifier = MacOSNativeNotifier()
    with patch("quota_monitor.notifiers.macos_native.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        notifier.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    cmd = run.call_args[0][0]
    assert cmd[0] == "osascript"
    assert "-e" in cmd


def test_send_raises_non_retryable_on_nonzero_exit():
    notifier = MacOSNativeNotifier()
    with patch("quota_monitor.notifiers.macos_native.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1, stderr="boom")
        with pytest.raises(NotifierError) as exc:
            notifier.send(Alert(title="t", body="b", reset_at=1, source="claude"))
    assert exc.value.retryable is False


def test_escapes_quotes_in_body():
    notifier = MacOSNativeNotifier()
    with patch("quota_monitor.notifiers.macos_native.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        notifier.send(Alert(title='ti"tle', body="bo\\dy", reset_at=1, source="claude"))
    script = run.call_args[0][0][-1]
    assert "\\\"" in script or '\\"' in script
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_notifier_macos.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/notifiers/macos_native.py`**

```python
import subprocess

from . import Alert, NotifierError


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


class MacOSNativeNotifier:
    name = "macos_native"

    def send(self, alert: Alert) -> None:
        title = _escape(alert.title)
        body = _escape(alert.body)
        script = f'display notification "{body}" with title "{title}"'
        try:
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired as e:
            raise NotifierError("osascript timed out", retryable=True) from e
        except FileNotFoundError as e:
            raise NotifierError("osascript not available (not macOS?)", retryable=False) from e
        if result.returncode != 0:
            raise NotifierError(f"osascript failed: {result.stderr.strip()}", retryable=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_notifier_macos.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/notifiers/macos_native.py tests/test_notifier_macos.py
git commit -m "feat(notifiers): macOS native osascript fallback"
```

---

## Task 13: `notifiers/cloudflare_relay.py`

**Files:**
- Create: `quota_monitor/notifiers/cloudflare_relay.py`
- Test: `tests/test_notifier_cf.py`

- [ ] **Step 1: Write failing tests**

`tests/test_notifier_cf.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_notifier_cf.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/notifiers/cloudflare_relay.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_notifier_cf.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/notifiers/cloudflare_relay.py tests/test_notifier_cf.py
git commit -m "feat(notifiers): cloudflare relay POST with retry classification"
```

---

## Task 14: `core/dispatch.py` retry + fallback

**Files:**
- Create: `quota_monitor/core/dispatch.py`
- Test: `tests/test_dispatch.py`

- [ ] **Step 1: Write failing tests**

`tests/test_dispatch.py`:
```python
from unittest.mock import MagicMock, patch
import pytest
from quota_monitor.notifiers import Alert, NotifierError
from quota_monitor.core.dispatch import dispatch_alert, DispatchOutcome


def _make_alert():
    return Alert(title="t", body="b", reset_at=1, source="claude")


def test_dispatch_uses_primary_when_it_succeeds():
    primary = MagicMock(name="primary")
    fallback = MagicMock(name="fallback")
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=fallback, retry_delays=())
    assert outcome == DispatchOutcome.PRIMARY_SUCCESS
    primary.send.assert_called_once()
    fallback.send.assert_not_called()


def test_dispatch_retries_primary_on_retryable_error():
    primary = MagicMock(name="primary")
    primary.send.side_effect = [NotifierError("x", retryable=True), NotifierError("x", retryable=True), None]
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=None, retry_delays=(0, 0))
    assert outcome == DispatchOutcome.PRIMARY_SUCCESS
    assert primary.send.call_count == 3


def test_dispatch_skips_retry_on_non_retryable_and_uses_fallback():
    primary = MagicMock(name="primary")
    primary.send.side_effect = NotifierError("auth", retryable=False)
    fallback = MagicMock(name="fallback")
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=fallback, retry_delays=(0, 0, 0))
    assert outcome == DispatchOutcome.FALLBACK_SUCCESS
    primary.send.assert_called_once()
    fallback.send.assert_called_once()


def test_dispatch_returns_total_failure_when_both_fail():
    primary = MagicMock(name="primary")
    primary.send.side_effect = NotifierError("x", retryable=False)
    fallback = MagicMock(name="fallback")
    fallback.send.side_effect = NotifierError("y", retryable=False)
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=fallback, retry_delays=())
    assert outcome == DispatchOutcome.TOTAL_FAILURE


def test_dispatch_returns_failure_when_no_fallback_and_primary_fails():
    primary = MagicMock(name="primary")
    primary.send.side_effect = NotifierError("x", retryable=False)
    outcome = dispatch_alert(_make_alert(), primary=primary, fallback=None, retry_delays=())
    assert outcome == DispatchOutcome.TOTAL_FAILURE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_dispatch.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/core/dispatch.py`**

```python
import enum
import sys
import time
from typing import Optional

from ..notifiers import Alert, Notifier, NotifierError

DEFAULT_RETRY_DELAYS = (1.0, 3.0, 9.0)


class DispatchOutcome(enum.Enum):
    PRIMARY_SUCCESS = "primary_success"
    FALLBACK_SUCCESS = "fallback_success"
    TOTAL_FAILURE = "total_failure"


def _try_send(notifier: Notifier, alert: Alert, retry_delays: tuple[float, ...]) -> bool:
    attempts = 1 + len(retry_delays)
    for i in range(attempts):
        try:
            notifier.send(alert)
            return True
        except NotifierError as e:
            print(f"[warn] {notifier.name} send failed: {e} (retryable={e.retryable})", file=sys.stderr)
            if not e.retryable or i == attempts - 1:
                return False
            time.sleep(retry_delays[i])
    return False


def dispatch_alert(
    alert: Alert,
    *,
    primary: Notifier,
    fallback: Optional[Notifier],
    retry_delays: tuple[float, ...] = DEFAULT_RETRY_DELAYS,
) -> DispatchOutcome:
    if _try_send(primary, alert, retry_delays):
        return DispatchOutcome.PRIMARY_SUCCESS
    if fallback is None:
        return DispatchOutcome.TOTAL_FAILURE
    if _try_send(fallback, alert, retry_delays=()):
        return DispatchOutcome.FALLBACK_SUCCESS
    return DispatchOutcome.TOTAL_FAILURE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_dispatch.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/core/dispatch.py tests/test_dispatch.py
git commit -m "feat(core): dispatch with retry on transient errors and fallback notifier"
```

---

## Task 15: `i18n/` t() + en/zh messages

**Files:**
- Create: `quota_monitor/i18n/__init__.py`
- Create: `quota_monitor/i18n/messages/__init__.py`
- Create: `quota_monitor/i18n/messages/en.py`
- Create: `quota_monitor/i18n/messages/zh.py`
- Test: `tests/test_i18n.py`

- [ ] **Step 1: Write failing tests**

`tests/test_i18n.py`:
```python
import pytest
from quota_monitor.i18n import t, set_locale


def test_t_returns_english_by_default():
    set_locale("en")
    assert "Quota recovered" in t("alert.title.recovered", source="Claude")


def test_t_substitutes_keyword_args():
    set_locale("en")
    msg = t("alert.body.recovered", source="Claude", reset_at_human="14:30 UTC")
    assert "Claude" in msg
    assert "14:30" in msg


def test_t_switches_to_zh():
    set_locale("zh")
    msg = t("alert.title.recovered", source="Claude")
    assert "Claude" in msg
    # Either has "额度" or "已恢复" or another Chinese token.
    assert any(c >= "一" for c in msg)


def test_t_unknown_key_returns_key_with_warning():
    set_locale("en")
    msg = t("nonexistent.key")
    assert "nonexistent.key" in msg


def test_invalid_locale_raises():
    with pytest.raises(ValueError):
        set_locale("ja")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_i18n.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/i18n/messages/__init__.py`** — empty file.

- [ ] **Step 4: Write `quota_monitor/i18n/messages/en.py`**

```python
MESSAGES = {
    "alert.title.recovered": "⏳ {source} quota recovered",
    "alert.body.recovered": "Your {source} 5-hour window has reset at {reset_at_human}. You can resume normal usage.",

    "wizard.welcome": "QuotaMonitor Setup Wizard",
    "wizard.preflight.ok": "Preflight checks passed.",
    "wizard.preflight.fail": "Preflight failed: {missing}. See README §Setup.",
    "wizard.complete": "Setup complete. First scan in ~5 minutes.",
    "wizard.keepalive.warning": (
        "⚠️ Keepalive risks:\n"
        "  1. ToS — Anthropic AUP may classify automated keepalive as abuse.\n"
        "  2. Sleep — both polling and seamless strategies stop working while macOS sleeps.\n"
        "     The natural 5h reset still happens; keepalive cannot save it.\n"
    ),

    "cli.status.no_state": "No state yet. Run `quota-monitor run` first.",
    "cli.status.window": "{source} window: starts {start}, resets {reset}",

    "log.probe_failed": "[warn] {source} probe failed: {error}",
    "log.state_corrupted": "[warn] state file corrupted ({error}); resetting to defaults",
    "log.keepalive_fired": "[info] keepalive sent: {phrase}",
}
```

- [ ] **Step 5: Write `quota_monitor/i18n/messages/zh.py`**

```python
MESSAGES = {
    "alert.title.recovered": "⏳ {source} 额度已恢复",
    "alert.body.recovered": "你的 {source} 5 小时窗口已于 {reset_at_human} 重置,可以继续使用了。",

    "wizard.welcome": "QuotaMonitor 配置向导",
    "wizard.preflight.ok": "前置检查通过。",
    "wizard.preflight.fail": "前置检查失败:{missing}。请参考 README §Setup。",
    "wizard.complete": "配置完成。约 5 分钟后首次扫描。",
    "wizard.keepalive.warning": (
        "⚠️ Keepalive 风险:\n"
        "  1. ToS — Anthropic AUP 可能将自动 keepalive 归类为滥用。\n"
        "  2. 睡眠 — polling 与 seamless 在 macOS 睡眠期间都会停止工作。\n"
        "     自然 5h 重置仍会发生;keepalive 无法挽救。\n"
    ),

    "cli.status.no_state": "尚无状态。请先运行 `quota-monitor run`。",
    "cli.status.window": "{source} 窗口:起 {start},终 {reset}",

    "log.probe_failed": "[warn] {source} probe 失败:{error}",
    "log.state_corrupted": "[warn] 状态文件损坏 ({error});重置为默认",
    "log.keepalive_fired": "[info] keepalive 已发送:{phrase}",
}
```

- [ ] **Step 6: Write `quota_monitor/i18n/__init__.py`**

```python
from .messages import en, zh

_TABLES = {"en": en.MESSAGES, "zh": zh.MESSAGES}
_current_locale = "en"


def set_locale(locale: str) -> None:
    global _current_locale
    if locale not in _TABLES:
        raise ValueError(f"unsupported locale: {locale}. Supported: {list(_TABLES)}")
    _current_locale = locale


def t(key: str, **kwargs) -> str:
    table = _TABLES[_current_locale]
    template = table.get(key)
    if template is None:
        return f"[missing i18n key: {key}]"
    try:
        return template.format(**kwargs)
    except KeyError as e:
        return f"[i18n format error in {key}: missing {e}]"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_i18n.py -v`
Expected: PASS (5 tests).

- [ ] **Step 8: Commit**

```bash
git add quota_monitor/i18n/ tests/test_i18n.py
git commit -m "feat(i18n): minimal t() with en + zh message tables"
```

---

## Task 16: `keepalive/phrases.py` no-repeat sampling

**Files:**
- Create: `quota_monitor/keepalive/__init__.py`
- Create: `quota_monitor/keepalive/phrases.py`
- Test: `tests/test_keepalive_phrases.py`

- [ ] **Step 1: Write failing tests**

`tests/test_keepalive_phrases.py`:
```python
from quota_monitor.keepalive.phrases import (
    DEFAULT_PHRASES, pick_phrase, PhraseState,
)


def test_default_pool_has_ten_phrases():
    assert len(DEFAULT_PHRASES) == 10
    assert len(set(DEFAULT_PHRASES)) == 10


def test_pick_returns_unused_phrase():
    pool = ("a", "b", "c")
    state = PhraseState(used_indices=(0, 1), size_at_init=3)
    phrase, new_state = pick_phrase(pool, state, rng=lambda seq: seq[0])
    assert phrase == "c"
    assert set(new_state.used_indices) == {0, 1, 2}


def test_pick_resets_when_pool_full():
    pool = ("a", "b")
    state = PhraseState(used_indices=(0, 1), size_at_init=2)
    phrase, new_state = pick_phrase(pool, state, rng=lambda seq: seq[0])
    # All exhausted -> reset before picking.
    assert phrase in pool
    assert len(new_state.used_indices) == 1


def test_pick_resets_when_pool_size_changes():
    state = PhraseState(used_indices=(0, 1, 2), size_at_init=3)
    pool = ("a", "b", "c", "d", "e")  # user added phrases
    phrase, new_state = pick_phrase(pool, state, rng=lambda seq: seq[0])
    assert phrase in pool
    assert new_state.size_at_init == 5
    assert len(new_state.used_indices) == 1


def test_uses_default_pool_when_user_pool_empty():
    state = PhraseState()
    phrase, new_state = pick_phrase((), state, rng=lambda seq: seq[0])
    assert phrase in DEFAULT_PHRASES
    assert new_state.size_at_init == len(DEFAULT_PHRASES)


def test_full_cycle_no_duplicates_within_pool():
    pool = ("a", "b", "c", "d", "e")
    state = PhraseState()
    seen = []
    rng = lambda seq: seq[0]  # deterministic
    for _ in range(len(pool)):
        phrase, state = pick_phrase(pool, state, rng=rng)
        seen.append(phrase)
    assert sorted(seen) == sorted(pool)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_keepalive_phrases.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/keepalive/__init__.py`** — empty file.

- [ ] **Step 4: Write `quota_monitor/keepalive/phrases.py`**

```python
"""Phrase pool for keepalive content randomization.

The pool reduces content fingerprinting. It does NOT defeat pattern-based
detection (request timing, token volume, session shape). See README §Risks.
"""
import random
from dataclasses import dataclass
from typing import Callable, Sequence

DEFAULT_PHRASES: tuple[str, ...] = (
    "hi", "hello", "hey", "yo", "thanks",
    "morning", "你好", "嗨", "👋", "ok",
)


@dataclass(frozen=True)
class PhraseState:
    used_indices: tuple[int, ...] = ()
    size_at_init: int = 0


def pick_phrase(
    pool: Sequence[str],
    state: PhraseState,
    *,
    rng: Callable[[Sequence[int]], int] = random.choice,
) -> tuple[str, PhraseState]:
    """Pick a phrase with no-repeat semantics. Returns (phrase, new_state)."""
    if not pool:
        pool = DEFAULT_PHRASES
    pool_size = len(pool)
    # Reset if pool changed or all exhausted.
    used = state.used_indices
    if state.size_at_init != pool_size:
        used = ()
    if len(used) >= pool_size:
        used = ()
    available = [i for i in range(pool_size) if i not in used]
    chosen_idx = rng(available)
    phrase = pool[chosen_idx]
    return phrase, PhraseState(
        used_indices=tuple(sorted(used + (chosen_idx,))),
        size_at_init=pool_size,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_keepalive_phrases.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/keepalive/ tests/test_keepalive_phrases.py
git commit -m "feat(keepalive): phrase pool with no-repeat sampling and reset-on-resize"
```

---

## Task 17: `keepalive/activity.py` + `keepalive/runner.py`

**Files:**
- Create: `quota_monitor/keepalive/activity.py`
- Create: `quota_monitor/keepalive/runner.py`
- Test: `tests/test_keepalive_activity.py`
- Test: `tests/test_keepalive_runner.py`

- [ ] **Step 1: Write failing tests**

`tests/test_keepalive_activity.py`:
```python
from quota_monitor.keepalive.activity import is_idle


def test_is_idle_true_when_no_recent_activity():
    assert is_idle(timestamps=(), now=1000.0, idle_seconds=3600) is True


def test_is_idle_false_when_recent_activity():
    assert is_idle(timestamps=(990.0,), now=1000.0, idle_seconds=3600) is False


def test_is_idle_true_when_all_activity_old():
    assert is_idle(timestamps=(100.0, 200.0), now=5000.0, idle_seconds=3600) is True


def test_is_idle_boundary_inclusive():
    # exactly idle_seconds ago should count as still recent
    assert is_idle(timestamps=(0.0,), now=3600.0, idle_seconds=3600) is False
```

`tests/test_keepalive_runner.py`:
```python
from unittest.mock import patch, MagicMock
from quota_monitor.keepalive.runner import run_keepalive


def test_runner_invokes_claude_cli_with_phrase_and_model():
    with patch("quota_monitor.keepalive.runner.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        ok = run_keepalive(claude_cli="/opt/claude", shell="/bin/zsh", phrase="hello", model="haiku")
    assert ok is True
    cmd = run.call_args[0][0]
    assert "/bin/zsh" in cmd
    full = " ".join(cmd)
    assert "/opt/claude" in full
    assert "hello" in full
    assert "haiku" in full


def test_runner_returns_false_on_nonzero_exit():
    with patch("quota_monitor.keepalive.runner.subprocess.run") as run:
        run.return_value = MagicMock(returncode=1, stderr="boom")
        ok = run_keepalive(claude_cli="/opt/claude", shell="/bin/zsh", phrase="hi", model="haiku")
    assert ok is False


def test_runner_returns_false_on_timeout():
    import subprocess as sp
    with patch("quota_monitor.keepalive.runner.subprocess.run", side_effect=sp.TimeoutExpired(cmd="x", timeout=1)):
        ok = run_keepalive(claude_cli="/opt/claude", shell="/bin/zsh", phrase="hi", model="haiku")
    assert ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_keepalive_activity.py tests/test_keepalive_runner.py -v`
Expected: FAIL with import errors.

- [ ] **Step 3: Write `quota_monitor/keepalive/activity.py`**

```python
def is_idle(*, timestamps: tuple[float, ...], now: float, idle_seconds: int) -> bool:
    """True if no timestamp is within `idle_seconds` of `now`."""
    cutoff = now - idle_seconds
    return not any(ts > cutoff for ts in timestamps)
```

- [ ] **Step 4: Write `quota_monitor/keepalive/runner.py`**

```python
import shlex
import subprocess
import sys


def run_keepalive(*, claude_cli: str, shell: str, phrase: str, model: str, timeout: int = 60) -> bool:
    """Invoke claude CLI to send a single keepalive message. Returns True on success."""
    quoted_phrase = shlex.quote(phrase)
    inner = f"{shlex.quote(claude_cli)} -p {quoted_phrase} --model {shlex.quote(model)} --no-session-persistence"
    cmd = [shell, "-lc", inner]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[error] keepalive timed out after {timeout}s", file=sys.stderr)
        return False
    except FileNotFoundError as e:
        print(f"[error] shell not found: {e}", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"[error] keepalive failed (rc={result.returncode}): {result.stderr.strip()}", file=sys.stderr)
        return False
    return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_keepalive_activity.py tests/test_keepalive_runner.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/keepalive/activity.py quota_monitor/keepalive/runner.py tests/test_keepalive_activity.py tests/test_keepalive_runner.py
git commit -m "feat(keepalive): activity idle check + subprocess runner"
```

---

## Task 18: `keepalive/polling.py`

> **State-free window:** polling computes the active window via `replay_windows(timestamps)` instead of reading state. Consistent with Task 9's fix.

**Files:**
- Create: `quota_monitor/keepalive/polling.py`
- Test: `tests/test_keepalive_polling.py`

- [ ] **Step 1: Write failing tests**

`tests/test_keepalive_polling.py`:
```python
from unittest.mock import patch
from quota_monitor.core.state import State
from quota_monitor.core.window import WINDOW_SECONDS
from quota_monitor.keepalive.polling import polling_tick, PollingDecision


def test_no_action_when_window_active_and_recent_activity():
    # 5 timestamps within last 30 min -> latest window's reset is in future, and is_idle False.
    now = 1_000_000.0
    ts = tuple(now - 60 * i for i in range(5))
    decision, _ = polling_tick(
        state=State(), now=now, timestamps=ts,
        idle_seconds=5 * 3600, claude_cli="/c", shell="/sh",
        model="haiku", phrase_pool=(),
    )
    assert decision is PollingDecision.SKIP


def test_fires_keepalive_when_no_history_at_all():
    state = State()
    with patch("quota_monitor.keepalive.polling.run_keepalive", return_value=True) as run:
        decision, new_state = polling_tick(
            state=state, now=1_000_000, timestamps=(),
            idle_seconds=5 * 3600, claude_cli="/c", shell="/sh",
            model="haiku", phrase_pool=("a",),
        )
    assert decision is PollingDecision.FIRED
    run.assert_called_once()
    assert new_state.keepalive.phrase_pool_size_at_init == 1


def test_fires_keepalive_when_latest_window_already_reset():
    # Latest window started long ago — its reset is in the past now.
    now = 1_000_000.0
    ts = (now - WINDOW_SECONDS - 100,)  # one stale activity outside any active window
    with patch("quota_monitor.keepalive.polling.run_keepalive", return_value=True):
        decision, _ = polling_tick(
            state=State(), now=now, timestamps=ts,
            idle_seconds=5 * 3600, claude_cli="/c", shell="/sh",
            model="haiku", phrase_pool=("a",),
        )
    assert decision is PollingDecision.FIRED


def test_fires_when_window_active_but_idle_threshold_exceeded():
    # Window opened recently but no activity in last `idle_seconds` -> still keepalive.
    now = 1_000_000.0
    ts = (now - 60 * 60,)  # 1h ago, only one activity, idle_seconds=5h means is_idle True
    with patch("quota_monitor.keepalive.polling.run_keepalive", return_value=True):
        decision, _ = polling_tick(
            state=State(), now=now, timestamps=ts,
            idle_seconds=30 * 60, claude_cli="/c", shell="/sh",   # idle threshold 30 min
            model="haiku", phrase_pool=("a",),
        )
    assert decision is PollingDecision.FIRED


def test_failure_does_not_mutate_phrase_state():
    state = State()
    with patch("quota_monitor.keepalive.polling.run_keepalive", return_value=False):
        decision, new_state = polling_tick(
            state=state, now=1_000_000, timestamps=(),
            idle_seconds=5 * 3600, claude_cli="/c", shell="/sh",
            model="haiku", phrase_pool=("a",),
        )
    assert decision is PollingDecision.FAILED
    assert new_state.keepalive == state.keepalive
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_keepalive_polling.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/keepalive/polling.py`**

```python
import enum
import random
from dataclasses import replace
from typing import Sequence

from ..core.state import State
from ..core.window import replay_windows
from .activity import is_idle
from .phrases import PhraseState, pick_phrase
from .runner import run_keepalive


class PollingDecision(enum.Enum):
    SKIP = "skip"        # window active and recent activity present
    FIRED = "fired"      # keepalive successfully sent
    FAILED = "failed"    # attempted but subprocess returned non-zero


def polling_tick(
    *,
    state: State,
    now: float,
    timestamps: tuple[float, ...],
    idle_seconds: int,
    claude_cli: str,
    shell: str,
    model: str,
    phrase_pool: Sequence[str],
) -> tuple[PollingDecision, State]:
    window = replay_windows(timestamps)
    window_active = window is not None and now < window.reset
    if window_active and not is_idle(timestamps=timestamps, now=now, idle_seconds=idle_seconds):
        return PollingDecision.SKIP, state

    phrase_state = PhraseState(
        used_indices=state.keepalive.phrase_pool_used_indices,
        size_at_init=state.keepalive.phrase_pool_size_at_init,
    )
    phrase, new_phrase_state = pick_phrase(phrase_pool, phrase_state, rng=random.choice)
    ok = run_keepalive(claude_cli=claude_cli, shell=shell, phrase=phrase, model=model)
    if not ok:
        return PollingDecision.FAILED, state

    new_keepalive = replace(
        state.keepalive,
        phrase_pool_used_indices=new_phrase_state.used_indices,
        phrase_pool_size_at_init=new_phrase_state.size_at_init,
    )
    return PollingDecision.FIRED, replace(state, keepalive=new_keepalive)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_keepalive_polling.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/keepalive/polling.py tests/test_keepalive_polling.py
git commit -m "feat(keepalive): polling strategy with idle/window check"
```

---

## Task 19: `keepalive/seamless.py` (port original tmux)

> **State-free window:** seamless also computes the window via `replay_windows(timestamps)`. State JSON only records "did we already schedule this reset?".

**Files:**
- Create: `quota_monitor/keepalive/seamless.py`
- Test: `tests/test_keepalive_seamless.py`

- [ ] **Step 1: Write failing tests**

`tests/test_keepalive_seamless.py`:
```python
from dataclasses import replace
from unittest.mock import patch
from quota_monitor.core.state import State, KeepaliveState
from quota_monitor.core.window import WINDOW_SECONDS
from quota_monitor.keepalive.seamless import seamless_tick, SeamlessDecision


def test_skip_no_window_when_no_timestamps():
    decision, _ = seamless_tick(
        state=State(), now=1000, timestamps=(),
        claude_cli="/c", shell="/sh", model="haiku", phrase_pool=(),
        trigger_minutes=30, buffer_seconds=60,
    )
    assert decision is SeamlessDecision.SKIP_NO_WINDOW


def test_skip_outside_when_far_from_reset():
    now = 1000.0
    ts = (now - 60,)   # 1 min ago -> latest window reset is now+5h-60s, far from trigger
    decision, _ = seamless_tick(
        state=State(), now=now, timestamps=ts,
        claude_cli="/c", shell="/sh", model="haiku", phrase_pool=(),
        trigger_minutes=30, buffer_seconds=60,
    )
    assert decision is SeamlessDecision.SKIP_OUTSIDE


def test_schedules_tmux_inside_trigger_window():
    # Latest window opens at (now - WINDOW_SECONDS + 500): reset is now + 500
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    expected_reset = (now - WINDOW_SECONDS + 500) + WINDOW_SECONDS
    with patch("quota_monitor.keepalive.seamless.subprocess.run") as run:
        run.return_value.returncode = 0
        decision, new_state = seamless_tick(
            state=State(), now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
        )
    assert decision is SeamlessDecision.SCHEDULED
    cmd = run.call_args[0][0]
    assert cmd[0] == "tmux"
    assert new_state.keepalive.last_seamless_scheduled_for == int(expected_reset)


def test_skip_already_scheduled_for_same_reset():
    now = 10_000.0
    ts = (now - WINDOW_SECONDS + 500,)
    expected_reset = int((now - WINDOW_SECONDS + 500) + WINDOW_SECONDS)
    state = replace(State(), keepalive=KeepaliveState(last_seamless_scheduled_for=expected_reset))
    with patch("quota_monitor.keepalive.seamless.subprocess.run") as run:
        decision, _ = seamless_tick(
            state=state, now=now, timestamps=ts,
            claude_cli="/c", shell="/sh", model="haiku", phrase_pool=("a",),
            trigger_minutes=30, buffer_seconds=60,
        )
    assert decision is SeamlessDecision.SKIP_ALREADY_SCHEDULED
    run.assert_not_called()


def test_skip_expired_when_only_old_activity():
    # Only activity is from 2 full windows ago -> latest window reset is in the past.
    now = 100_000.0
    ts = (now - 2 * WINDOW_SECONDS,)
    decision, _ = seamless_tick(
        state=State(), now=now, timestamps=ts,
        claude_cli="/c", shell="/sh", model="haiku", phrase_pool=(),
        trigger_minutes=30, buffer_seconds=60,
    )
    assert decision is SeamlessDecision.SKIP_EXPIRED
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_keepalive_seamless.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/keepalive/seamless.py`**

```python
import enum
import random
import shlex
import subprocess
import sys
import time
from dataclasses import replace
from typing import Sequence

from ..core.state import State
from ..core.window import replay_windows
from .phrases import PhraseState, pick_phrase


class SeamlessDecision(enum.Enum):
    SKIP_NO_WINDOW = "skip_no_window"           # no activity -> no window to chase
    SKIP_OUTSIDE = "skip_outside"               # > trigger minutes left
    SKIP_EXPIRED = "skip_expired"               # window already reset
    SKIP_ALREADY_SCHEDULED = "skip_scheduled"   # already scheduled this reset
    SCHEDULED = "scheduled"                     # tmux scheduled successfully
    FAILED = "failed"                           # tmux invocation failed


def seamless_tick(
    *,
    state: State,
    now: float,
    timestamps: tuple[float, ...],
    claude_cli: str,
    shell: str,
    model: str,
    phrase_pool: Sequence[str],
    trigger_minutes: int,
    buffer_seconds: int,
) -> tuple[SeamlessDecision, State]:
    window = replay_windows(timestamps)
    if window is None:
        return SeamlessDecision.SKIP_NO_WINDOW, state
    time_to_reset = window.reset - now
    if time_to_reset <= 0:
        return SeamlessDecision.SKIP_EXPIRED, state
    if time_to_reset > trigger_minutes * 60:
        return SeamlessDecision.SKIP_OUTSIDE, state
    if state.keepalive.last_seamless_scheduled_for == int(window.reset):
        return SeamlessDecision.SKIP_ALREADY_SCHEDULED, state

    phrase_state = PhraseState(
        used_indices=state.keepalive.phrase_pool_used_indices,
        size_at_init=state.keepalive.phrase_pool_size_at_init,
    )
    phrase, new_phrase_state = pick_phrase(phrase_pool, phrase_state, rng=random.choice)

    delay = int(time_to_reset) + buffer_seconds
    quoted_phrase = shlex.quote(phrase)
    inner = (
        f"{shlex.quote(claude_cli)} -p {quoted_phrase} "
        f"--model {shlex.quote(model)} --no-session-persistence"
    )
    session_name = f"qm_keepalive_{int(time.time())}"
    tmux_cmd = ["tmux", "new-session", "-d", "-s", session_name,
                f"sleep {delay} && {shell} -lc {shlex.quote(inner)}"]
    try:
        result = subprocess.run(tmux_cmd, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"[error] tmux schedule failed: {e}", file=sys.stderr)
        return SeamlessDecision.FAILED, state
    if result.returncode != 0:
        print(f"[error] tmux returned {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        return SeamlessDecision.FAILED, state

    new_keepalive = replace(
        state.keepalive,
        last_seamless_scheduled_for=int(window.reset),
        phrase_pool_used_indices=new_phrase_state.used_indices,
        phrase_pool_size_at_init=new_phrase_state.size_at_init,
    )
    return SeamlessDecision.SCHEDULED, replace(state, keepalive=new_keepalive)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_keepalive_seamless.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/keepalive/seamless.py tests/test_keepalive_seamless.py
git commit -m "feat(keepalive): seamless strategy via tmux + sleep with reset dedupe"
```

---

## Task 20: `platform/schedule.py` LaunchAgent plist

**Files:**
- Create: `quota_monitor/platform/schedule.py`
- Test: `tests/test_platform_schedule.py`

- [ ] **Step 1: Write failing tests**

`tests/test_platform_schedule.py`:
```python
from pathlib import Path
from unittest.mock import patch, MagicMock
from quota_monitor.platform.schedule import (
    generate_launch_agent_plist, install_launch_agent, uninstall_launch_agent,
)


def test_plist_contains_label_program_and_interval(tmp_path):
    plist = generate_launch_agent_plist(
        label="io.github.frank.qm",
        program_arguments=["/usr/bin/python3.11", "-m", "quota_monitor", "run"],
        interval_seconds=300,
        stdout_log=tmp_path / "out.log",
        stderr_log=tmp_path / "err.log",
    )
    assert "<key>Label</key>" in plist
    assert "<string>io.github.frank.qm</string>" in plist
    assert "<key>ProgramArguments</key>" in plist
    assert "<string>/usr/bin/python3.11</string>" in plist
    assert "<key>StartInterval</key>" in plist
    assert "<integer>300</integer>" in plist
    assert "<key>RunAtLoad</key>" in plist
    assert "<true/>" in plist


def test_install_writes_file_and_calls_launchctl(tmp_path):
    plist_path = tmp_path / "agent.plist"
    with patch("quota_monitor.platform.schedule.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        install_launch_agent(plist_path=plist_path, plist_content="<plist/>")
    assert plist_path.read_text() == "<plist/>"
    run.assert_called_once()
    cmd = run.call_args[0][0]
    assert cmd[0] == "launchctl"
    assert "load" in cmd


def test_uninstall_calls_launchctl_unload_and_removes_file(tmp_path):
    plist_path = tmp_path / "agent.plist"
    plist_path.write_text("<plist/>")
    with patch("quota_monitor.platform.schedule.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0, stderr="")
        uninstall_launch_agent(plist_path=plist_path)
    assert not plist_path.exists()
    run.assert_called_once()
    cmd = run.call_args[0][0]
    assert "unload" in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_platform_schedule.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/platform/schedule.py`**

```python
import subprocess
import sys
from pathlib import Path


def generate_launch_agent_plist(
    *,
    label: str,
    program_arguments: list[str],
    interval_seconds: int,
    stdout_log: Path,
    stderr_log: Path,
) -> str:
    args_xml = "\n".join(f"    <string>{a}</string>" for a in program_arguments)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>StartInterval</key>
  <integer>{interval_seconds}</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{stdout_log}</string>
  <key>StandardErrorPath</key>
  <string>{stderr_log}</string>
</dict>
</plist>
"""


def install_launch_agent(*, plist_path: Path, plist_content: str) -> None:
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content)
    result = subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        print(f"[warn] launchctl load returned {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        print("  Try manually: launchctl load -w " + str(plist_path), file=sys.stderr)


def uninstall_launch_agent(*, plist_path: Path) -> None:
    if plist_path.exists():
        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            print(f"[warn] launchctl unload returned {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
        plist_path.unlink()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_platform_schedule.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add quota_monitor/platform/schedule.py tests/test_platform_schedule.py
git commit -m "feat(platform): LaunchAgent plist generator + install/uninstall"
```

---

## Task 21: `cli/run.py` main flow + integration test

**Files:**
- Create: `quota_monitor/cli/__init__.py`
- Create: `quota_monitor/cli/run.py`
- Modify: `quota_monitor/__main__.py` (wire `run` subcommand)
- Test: `tests/test_cli_run.py`

- [ ] **Step 1: Write failing test**

`tests/test_cli_run.py`:
```python
from pathlib import Path
from unittest.mock import patch, MagicMock
import json
from quota_monitor.cli.run import run_once


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
locale = "en"
[probes.claude]
enabled = true
threshold_turns = 5
window_hours = 5
[probes.codex]
enabled = false
[notifiers]
primary = "telegram"
fallback = ""
[notifiers.telegram]
[notifiers.cloudflare_relay]
enabled = false
[keepalive]
enabled = false
strategy = "polling"
""")
    return cfg


def _write_env(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=cid\n")
    return env


def test_run_once_writes_alerted_state_on_success(tmp_path):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    fake_probe_result = MagicMock(source="claude", timestamps=(1000.0,) * 6, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake_probe_result), \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        tg_instance = MagicMock(name="telegram"); tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=1010.0, dry_run=False,
        )
    assert rc == 0
    tg_instance.send.assert_called_once()
    saved = json.loads(state_path.read_text())
    assert saved["claude"]["alerted_for_reset"] == 1000 + 5 * 3600


def test_run_once_dry_run_does_not_send_or_save(tmp_path):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    fake_probe_result = MagicMock(source="claude", timestamps=(1000.0,) * 6, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake_probe_result), \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        tg_instance = MagicMock(); tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(
            config_path=cfg_path, env_path=env_path, state_path=state_path,
            now=1010.0, dry_run=True,
        )
    assert rc == 0
    tg_instance.send.assert_not_called()
    assert not state_path.exists()


def test_run_once_returns_nonzero_when_config_missing(tmp_path):
    rc = run_once(
        config_path=tmp_path / "nope.toml",
        env_path=tmp_path / ".env",
        state_path=tmp_path / "state.json",
        now=1010.0, dry_run=False,
    )
    assert rc != 0


def test_run_once_does_not_realert_in_same_window(tmp_path):
    cfg_path = _write_config(tmp_path)
    env_path = _write_env(tmp_path)
    state_path = tmp_path / "state.json"
    # Pre-seed state as if already alerted for this reset point (1000 + 5h).
    state_path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {"alerted_for_reset": 1000 + 5 * 3600},
        "codex": {"alerted_for_reset": 0, "cooldown_until": 0},
        "keepalive": {"last_seamless_scheduled_for": 0, "phrase_pool_used_indices": [], "phrase_pool_size_at_init": 0},
    }))
    fake = MagicMock(source="claude", timestamps=(1000.0,) * 6, extra={})
    with patch("quota_monitor.cli.run.scan_claude", return_value=fake), \
         patch("quota_monitor.cli.run.TelegramNotifier") as TG:
        tg_instance = MagicMock(); tg_instance.name = "telegram"
        TG.return_value = tg_instance
        rc = run_once(config_path=cfg_path, env_path=env_path, state_path=state_path, now=1010.0, dry_run=False)
    assert rc == 0
    tg_instance.send.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli_run.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/cli/__init__.py`** — empty file.

- [ ] **Step 4: Write `quota_monitor/cli/run.py`**

```python
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config.loader import ConfigError, load_config
from ..core.dispatch import DispatchOutcome, dispatch_alert
from ..core.state import ClaudeState, CodexState, State, load_state, save_state
from ..core.window import AlertDecision, decide_alerts, replay_windows
from ..i18n import set_locale, t
from ..notifiers import Alert, Notifier
from ..notifiers.cloudflare_relay import CloudflareRelayNotifier
from ..notifiers.macos_native import MacOSNativeNotifier
from ..notifiers.telegram import TelegramNotifier
from ..platform import paths as platform_paths
from ..probes.claude import scan_claude
from ..probes.codex import CodexAuthMissingError, scan_codex


def _build_notifier(name: str, cfg, secrets: dict[str, str]) -> Optional[Notifier]:
    if not name:
        return None
    if name == "telegram":
        return TelegramNotifier(
            bot_token=secrets.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=secrets.get("TELEGRAM_CHAT_ID", ""),
        )
    if name == "macos_native":
        return MacOSNativeNotifier()
    if name == "cloudflare_relay":
        return CloudflareRelayNotifier(webhook_url=cfg.notifiers.cloudflare_relay.webhook_url)
    print(f"[error] unknown notifier: {name}", file=sys.stderr)
    return None


def _alert_for(decision: AlertDecision) -> Alert:
    label = "Claude" if decision.source == "claude" else "Codex"
    reset_dt = datetime.fromtimestamp(decision.reset_at, tz=timezone.utc)
    reset_human = reset_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    return Alert(
        title=t("alert.title.recovered", source=label),
        body=t("alert.body.recovered", source=label, reset_at_human=reset_human),
        reset_at=decision.reset_at,
        source=decision.source,
    )


def run_once(
    *,
    config_path: Path,
    env_path: Path,
    state_path: Path,
    now: float,
    dry_run: bool,
) -> int:
    try:
        cfg = load_config(config_path, env_path)
    except ConfigError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    set_locale(cfg.locale)
    state = load_state(state_path)

    claude_result = None
    if cfg.probes.claude.enabled:
        try:
            claude_result = scan_claude(
                app_dir=platform_paths.claude_app_dir(),
                cli_dir=platform_paths.claude_cli_dir(),
                costs_file=platform_paths.claude_costs_file(),
                now=now,
                window_seconds=cfg.probes.claude.window_hours * 3600,
            )
        except Exception as e:
            print(t("log.probe_failed", source="claude", error=e), file=sys.stderr)

    codex_result = None
    if cfg.probes.codex.enabled:
        try:
            codex_result = scan_codex(auth_file=platform_paths.codex_auth_file())
        except CodexAuthMissingError as e:
            print(t("log.probe_failed", source="codex", error=e), file=sys.stderr)
        except Exception as e:
            print(t("log.probe_failed", source="codex", error=e), file=sys.stderr)

    # Full Replay: compute the latest Claude window from probe timestamps alone.
    # State never participates in window slicing — see core/window.py docstring.
    claude_window = replay_windows(claude_result.timestamps) if claude_result is not None else None

    decisions = decide_alerts(
        state=state,
        claude_window=claude_window,
        codex=codex_result,
        now=now,
        claude_threshold=cfg.probes.claude.threshold_turns,
        codex_threshold_percent=cfg.probes.codex.threshold_percent,
    )

    if dry_run:
        for d in decisions:
            print(f"[dry-run] would alert: source={d.source} reset_at={d.reset_at}")
        return 0

    primary = _build_notifier(cfg.notifiers.primary, cfg, cfg.secrets)
    fallback = _build_notifier(cfg.notifiers.fallback, cfg, cfg.secrets)
    if primary is None:
        print("[error] primary notifier could not be constructed", file=sys.stderr)
        return 3

    new_state = state
    for d in decisions:
        alert = _alert_for(d)
        outcome = dispatch_alert(alert, primary=primary, fallback=fallback)
        if outcome in (DispatchOutcome.PRIMARY_SUCCESS, DispatchOutcome.FALLBACK_SUCCESS):
            if d.source == "claude":
                new_state = replace(new_state, claude=ClaudeState(alerted_for_reset=d.reset_at))
            elif d.source == "codex":
                new_state = replace(new_state, codex=CodexState(
                    alerted_for_reset=d.reset_at, cooldown_until=d.reset_at,
                ))

    save_state(state_path, new_state)
    return 0
```

- [ ] **Step 5: Wire `__main__.py` to call `run_once`**

Modify `quota_monitor/__main__.py` — replace the body of `main()`:

```python
import argparse
import sys
import time
from pathlib import Path

from .platform import paths as platform_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quota_monitor")
    parser.add_argument("--version", action="version", version="quota_monitor 0.1.0")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("setup", help="interactive setup wizard")

    run_p = sub.add_parser("run", help="single scan (cron entry)")
    run_p.add_argument("--dry-run", action="store_true")

    sub.add_parser("status", help="show current state")
    nt = sub.add_parser("notify-test", help="send a test notification")
    nt.add_argument("--backend", default=None)
    sub.add_parser("uninstall", help="remove LaunchAgent")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0

    if args.cmd == "run":
        from .cli.run import run_once
        return run_once(
            config_path=platform_paths.config_file(),
            env_path=platform_paths.env_file(),
            state_path=platform_paths.state_file(),
            now=time.time(),
            dry_run=args.dry_run,
        )
    # other subcommands wired in later tasks
    print(f"[stub] {args.cmd} not yet implemented", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli_run.py -v`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add quota_monitor/cli/ quota_monitor/__main__.py tests/test_cli_run.py
git commit -m "feat(cli): run command integrates probes + decision + dispatch + state"
```

---

## Task 22: `cli/status.py`

**Files:**
- Create: `quota_monitor/cli/status.py`
- Modify: `quota_monitor/__main__.py` (wire `status`)
- Test: `tests/test_cli_status.py`

- [ ] **Step 1: Write failing test**

`tests/test_cli_status.py`:
```python
import json
from datetime import datetime, timezone
from quota_monitor.cli.status import show_status


def test_status_prints_no_state_when_missing(capsys, tmp_path):
    rc = show_status(state_path=tmp_path / "no.json", config_path=tmp_path / "no.toml")
    assert rc == 0
    out = capsys.readouterr().out
    assert "No state" in out or "no state" in out.lower()


def test_status_prints_last_alerted_reset(capsys, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "schema_version": 1,
        "claude": {"alerted_for_reset": 1747218000},
        "codex": {"alerted_for_reset": 0, "cooldown_until": 0},
        "keepalive": {"last_seamless_scheduled_for": 0, "phrase_pool_used_indices": [], "phrase_pool_size_at_init": 0},
    }))
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('locale="en"\n[notifiers]\nprimary="telegram"\n')
    rc = show_status(state_path=state_path, config_path=cfg_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "claude" in out.lower()
    assert datetime.fromtimestamp(1747218000, tz=timezone.utc).strftime("%Y-%m-%d") in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli_status.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/cli/status.py`**

```python
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..config.loader import ConfigError, load_config
from ..core.state import default_state, load_state
from ..i18n import set_locale, t


def _human(epoch: int) -> str:
    if epoch == 0:
        return "never"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def show_status(*, state_path: Path, config_path: Path) -> int:
    try:
        cfg = load_config(config_path, env_path=None)
        set_locale(cfg.locale)
    except ConfigError:
        pass  # status still works without config

    state = load_state(state_path)
    if state == default_state():
        print(t("cli.status.no_state"))
        return 0

    # state only stores last alerted reset; window itself is derived live via probes
    # if the user wants real-time window info, they should run `quota-monitor run --dry-run`.
    print(t("cli.status.window", source="claude",
            start="(derived live — run --dry-run)",
            reset=_human(state.claude.alerted_for_reset)))
    print(t("cli.status.window", source="codex",
            start="-",
            reset=_human(state.codex.alerted_for_reset)))
    if state.keepalive.last_seamless_scheduled_for:
        print(f"keepalive seamless scheduled for: {_human(state.keepalive.last_seamless_scheduled_for)}")
    print(f"keepalive phrase pool used: {len(state.keepalive.phrase_pool_used_indices)} / {state.keepalive.phrase_pool_size_at_init}")
    return 0
```

- [ ] **Step 4: Wire in `__main__.py`** — replace the `# other subcommands` branch with:

```python
    if args.cmd == "status":
        from .cli.status import show_status
        return show_status(
            state_path=platform_paths.state_file(),
            config_path=platform_paths.config_file(),
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli_status.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/cli/status.py quota_monitor/__main__.py tests/test_cli_status.py
git commit -m "feat(cli): status command shows windows and keepalive state"
```

---

## Task 23: `cli/notify_test.py`

**Files:**
- Create: `quota_monitor/cli/notify_test.py`
- Modify: `quota_monitor/__main__.py` (wire `notify-test`)
- Test: `tests/test_cli_notify_test.py`

- [ ] **Step 1: Write failing test**

`tests/test_cli_notify_test.py`:
```python
from pathlib import Path
from unittest.mock import patch, MagicMock
from quota_monitor.cli.notify_test import send_test


def _write_minimal_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text('locale="en"\n[notifiers]\nprimary="telegram"\n[notifiers.telegram]\n')
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=cid\n")
    return cfg, env


def test_sends_test_alert_via_primary(tmp_path):
    cfg, env = _write_minimal_config(tmp_path)
    with patch("quota_monitor.cli.notify_test.TelegramNotifier") as TG:
        instance = MagicMock(); instance.name = "telegram"
        TG.return_value = instance
        rc = send_test(config_path=cfg, env_path=env, backend=None)
    assert rc == 0
    instance.send.assert_called_once()


def test_send_test_specific_backend(tmp_path):
    cfg, env = _write_minimal_config(tmp_path)
    with patch("quota_monitor.cli.notify_test.MacOSNativeNotifier") as MN:
        instance = MagicMock(); instance.name = "macos_native"
        MN.return_value = instance
        rc = send_test(config_path=cfg, env_path=env, backend="macos_native")
    assert rc == 0
    instance.send.assert_called_once()


def test_send_test_returns_nonzero_on_unknown_backend(tmp_path):
    cfg, env = _write_minimal_config(tmp_path)
    rc = send_test(config_path=cfg, env_path=env, backend="zzz")
    assert rc != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli_notify_test.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/cli/notify_test.py`**

```python
import sys
from pathlib import Path
from typing import Optional

from ..config.loader import ConfigError, load_config
from ..i18n import set_locale
from ..notifiers import Alert
from ..notifiers.cloudflare_relay import CloudflareRelayNotifier
from ..notifiers.macos_native import MacOSNativeNotifier
from ..notifiers.telegram import TelegramNotifier


def send_test(*, config_path: Path, env_path: Path, backend: Optional[str]) -> int:
    try:
        cfg = load_config(config_path, env_path)
    except ConfigError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    set_locale(cfg.locale)

    name = backend or cfg.notifiers.primary
    if name == "telegram":
        notifier = TelegramNotifier(
            bot_token=cfg.secrets.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=cfg.secrets.get("TELEGRAM_CHAT_ID", ""),
        )
    elif name == "macos_native":
        notifier = MacOSNativeNotifier()
    elif name == "cloudflare_relay":
        notifier = CloudflareRelayNotifier(webhook_url=cfg.notifiers.cloudflare_relay.webhook_url)
    else:
        print(f"[error] unknown backend: {name}", file=sys.stderr)
        return 3

    alert = Alert(
        title="QuotaMonitor test",
        body="If you see this, your notifier is wired correctly.",
        reset_at=0,
        source="test",
    )
    try:
        notifier.send(alert)
    except Exception as e:
        print(f"[error] send failed: {e}", file=sys.stderr)
        return 4
    print(f"sent test via {name}")
    return 0
```

- [ ] **Step 4: Wire in `__main__.py`** — add branch:

```python
    if args.cmd == "notify-test":
        from .cli.notify_test import send_test
        return send_test(
            config_path=platform_paths.config_file(),
            env_path=platform_paths.env_file(),
            backend=args.backend,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli_notify_test.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/cli/notify_test.py quota_monitor/__main__.py tests/test_cli_notify_test.py
git commit -m "feat(cli): notify-test sends a verification message via chosen backend"
```

---

## Task 24: `cli/uninstall.py`

**Files:**
- Create: `quota_monitor/cli/uninstall.py`
- Modify: `quota_monitor/__main__.py` (wire `uninstall`)
- Test: `tests/test_cli_uninstall.py`

- [ ] **Step 1: Write failing test**

`tests/test_cli_uninstall.py`:
```python
from unittest.mock import patch
from quota_monitor.cli.uninstall import uninstall


def test_uninstall_calls_launchagent_remove(tmp_path):
    plist = tmp_path / "agent.plist"
    plist.write_text("<plist/>")
    with patch("quota_monitor.cli.uninstall.uninstall_launch_agent") as remove:
        rc = uninstall(launch_agent_label="io.x", plist_path=plist)
    assert rc == 0
    remove.assert_called_once_with(plist_path=plist)


def test_uninstall_is_noop_when_plist_missing(tmp_path, capsys):
    plist = tmp_path / "no.plist"
    rc = uninstall(launch_agent_label="io.x", plist_path=plist)
    assert rc == 0
    out = capsys.readouterr().out + capsys.readouterr().err
    # The function should still print guidance about config/state.
    assert "config" in (out.lower() + "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli_uninstall.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/cli/uninstall.py`**

```python
from pathlib import Path

from ..platform.schedule import uninstall_launch_agent


def uninstall(*, launch_agent_label: str, plist_path: Path) -> int:
    if plist_path.exists():
        uninstall_launch_agent(plist_path=plist_path)
        print(f"removed LaunchAgent: {plist_path}")
    else:
        print(f"no LaunchAgent at {plist_path} — nothing to do")
    print("NOTE: ~/.quota-monitor/ (config.toml, .env, state.json) was NOT touched.")
    print("      Remove manually if you want a complete wipe.")
    return 0
```

- [ ] **Step 4: Wire in `__main__.py`** — add branch:

```python
    if args.cmd == "uninstall":
        from .cli.uninstall import uninstall
        label = "io.github.frank.quotamonitor"
        return uninstall(
            launch_agent_label=label,
            plist_path=platform_paths.launch_agent_path(label),
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli_uninstall.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/cli/uninstall.py quota_monitor/__main__.py tests/test_cli_uninstall.py
git commit -m "feat(cli): uninstall removes LaunchAgent but preserves user data"
```

---

## Task 25: `cli/setup.py` wizard — preflight + steps 1-4, 6, 7 (skip CF)

> **Wizard rule:** never pause mid-flow to install something. Preflight checks **everything** up front; if anything is missing, exit with an actionable message pointing to README §Setup's AI-agent prep prompt. User goes away, runs the agent prep, comes back, re-runs `setup` — it completes uninterrupted.

**Files:**
- Create: `quota_monitor/cli/_input.py` (interactive input helpers)
- Create: `quota_monitor/cli/setup.py`
- Create: `quota_monitor/cli/_preflight.py`
- Modify: `quota_monitor/__main__.py` (wire `setup`)
- Test: `tests/test_wizard_smoke.py`
- Test fixture: `tests/fixtures/wizard_answers_basic.json`

- [ ] **Step 1: Write fixture for non-interactive smoke run**

`tests/fixtures/wizard_answers_basic.json`:
```json
{
  "locale": "en",
  "claude_enabled": true,
  "codex_enabled": false,
  "primary": "telegram",
  "fallback": "macos_native",
  "telegram_bot_token": "TEST_TOKEN",
  "telegram_chat_id": "TEST_CHAT",
  "skip_telegram_test": true,
  "keepalive_enabled": false,
  "schedule": "skip"
}
```

- [ ] **Step 2: Write failing test**

`tests/test_wizard_smoke.py`:
```python
import json
from pathlib import Path
from unittest.mock import patch
from quota_monitor.cli.setup import run_wizard

FIXTURES = Path(__file__).parent / "fixtures"


def test_wizard_non_interactive_writes_config_and_env(tmp_path):
    answers = json.loads((FIXTURES / "wizard_answers_basic.json").read_text())
    config_path = tmp_path / "config.toml"
    env_path = tmp_path / ".env"
    # Skip preflight strictness by stubbing it to "all green".
    with patch("quota_monitor.cli.setup.preflight_check", return_value=([], [])):
        rc = run_wizard(
            answers=answers,
            config_path=config_path,
            env_path=env_path,
            data_dir=tmp_path,
            non_interactive=True,
        )
    assert rc == 0
    cfg_text = config_path.read_text()
    assert 'locale = "en"' in cfg_text
    assert "[notifiers.cloudflare_relay]" in cfg_text
    assert "[keepalive]" in cfg_text
    env_text = env_path.read_text()
    assert "TELEGRAM_BOT_TOKEN=TEST_TOKEN" in env_text
    assert "TELEGRAM_CHAT_ID=TEST_CHAT" in env_text


def test_wizard_aborts_when_preflight_missing_required(tmp_path):
    answers = json.loads((FIXTURES / "wizard_answers_basic.json").read_text())
    with patch("quota_monitor.cli.setup.preflight_check",
               return_value=(["python>=3.11 missing"], [])):
        rc = run_wizard(
            answers=answers,
            config_path=tmp_path / "config.toml",
            env_path=tmp_path / ".env",
            data_dir=tmp_path,
            non_interactive=True,
        )
    assert rc != 0
    assert not (tmp_path / "config.toml").exists()


def test_wizard_keepalive_enabled_writes_strategy(tmp_path):
    answers = json.loads((FIXTURES / "wizard_answers_basic.json").read_text())
    answers["keepalive_enabled"] = True
    answers["keepalive_strategy"] = "polling"
    with patch("quota_monitor.cli.setup.preflight_check", return_value=([], [])):
        rc = run_wizard(
            answers=answers,
            config_path=tmp_path / "config.toml",
            env_path=tmp_path / ".env",
            data_dir=tmp_path,
            non_interactive=True,
        )
    assert rc == 0
    assert 'strategy = "polling"' in (tmp_path / "config.toml").read_text()
    assert "enabled = true" in (tmp_path / "config.toml").read_text()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_wizard_smoke.py -v`
Expected: FAIL with import error.

- [ ] **Step 4: Write `quota_monitor/cli/_input.py`**

```python
"""Tiny interactive input helpers — no third-party deps."""
import sys


def ask_choice(prompt: str, options: list[str], default: int = 0) -> int:
    """Show numbered options, return 0-based selected index."""
    print(prompt)
    for i, opt in enumerate(options, 1):
        marker = " [default]" if i - 1 == default else ""
        print(f"  [{i}] {opt}{marker}")
    while True:
        raw = input("> ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"please enter 1-{len(options)}")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        raw = input(prompt + suffix + " ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False


def ask_string(prompt: str, *, secret: bool = False) -> str:
    if secret:
        import getpass
        return getpass.getpass(prompt + ": ")
    return input(prompt + ": ").strip()
```

- [ ] **Step 5: Write `quota_monitor/cli/_preflight.py`**

```python
"""Preflight checks — runs before the wizard does anything mutating."""
import shutil
import subprocess
import sys
from pathlib import Path


def preflight_check(*, need_wrangler: bool = False) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors must be fixed before proceeding."""
    errors: list[str] = []
    warnings: list[str] = []

    if sys.version_info < (3, 11):
        errors.append(f"python>=3.11 required (have {sys.version_info.major}.{sys.version_info.minor})")

    if shutil.which("claude") is None:
        warnings.append("`claude` CLI not in PATH (only needed for keepalive feature)")

    if need_wrangler and shutil.which("wrangler") is None:
        errors.append("`wrangler` CLI required for Cloudflare relay setup; run: npm install -g wrangler")

    if need_wrangler:
        try:
            result = subprocess.run(["wrangler", "whoami"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                errors.append("not logged in to Cloudflare; run: wrangler login")
        except FileNotFoundError:
            pass  # already covered above

    return errors, warnings
```

- [ ] **Step 6: Write `quota_monitor/cli/setup.py`**

```python
import sys
from pathlib import Path
from typing import Optional

from ..i18n import set_locale, t
from ._input import ask_choice, ask_string, ask_yes_no
from ._preflight import preflight_check


def _render_config(answers: dict) -> str:
    keepalive_enabled = "true" if answers.get("keepalive_enabled") else "false"
    keepalive_strategy = answers.get("keepalive_strategy", "polling")
    primary = answers.get("primary", "telegram")
    fallback = answers.get("fallback", "")
    cf_enabled = "true" if answers.get("cloudflare_enabled") else "false"
    cf_url = answers.get("cloudflare_webhook_url", "")
    return f"""\
locale = "{answers.get("locale", "en")}"
log_level = "info"

[probes.claude]
enabled = {"true" if answers.get("claude_enabled", True) else "false"}
threshold_turns = 5
window_hours = 5

[probes.codex]
enabled = {"true" if answers.get("codex_enabled", False) else "false"}
threshold_percent = 30

[notifiers]
primary = "{primary}"
fallback = "{fallback}"

[notifiers.telegram]

[notifiers.cloudflare_relay]
enabled = {cf_enabled}
webhook_url = "{cf_url}"

[keepalive]
enabled = {keepalive_enabled}
strategy = "{keepalive_strategy}"
model = "haiku"
phrase_pool = []
seamless_trigger_minutes = 30
seamless_buffer_seconds = 60
"""


def _render_env(answers: dict) -> str:
    return (
        f"TELEGRAM_BOT_TOKEN={answers.get('telegram_bot_token', '')}\n"
        f"TELEGRAM_CHAT_ID={answers.get('telegram_chat_id', '')}\n"
    )


def _collect_interactive_answers() -> dict:
    """Walk the user through the wizard steps and return an answers dict."""
    answers: dict = {}

    print("\n=== (1/7) Language ===")
    locale_idx = ask_choice("Select language:", ["English", "中文"], default=0)
    answers["locale"] = "en" if locale_idx == 0 else "zh"
    set_locale(answers["locale"])

    print("\n=== (2/7) Services to monitor ===")
    answers["claude_enabled"] = ask_yes_no("Monitor Claude?", default=True)
    answers["codex_enabled"] = ask_yes_no("Monitor Codex (requires ~/.codex/auth.json)?", default=False)

    print("\n=== (3/7) Notification ===")
    primary_idx = ask_choice(
        "Primary notifier:",
        ["telegram (direct)", "macos_native", "cloudflare_relay (advanced)"],
        default=0,
    )
    answers["primary"] = ["telegram", "macos_native", "cloudflare_relay"][primary_idx]
    fallback_idx = ask_choice(
        "Fallback when primary fails:",
        ["macos_native", "(none)"],
        default=0,
    )
    answers["fallback"] = ["macos_native", ""][fallback_idx]

    print("\n=== (4/7) Telegram credentials ===")
    if answers["primary"] == "telegram" or answers["primary"] == "cloudflare_relay":
        answers["telegram_bot_token"] = ask_string("Bot token", secret=True)
        answers["telegram_chat_id"] = ask_string("Chat ID")
        answers["skip_telegram_test"] = not ask_yes_no("Send a test message?", default=True)
    else:
        answers["telegram_bot_token"] = ""
        answers["telegram_chat_id"] = ""

    # Step 5 (CF) is handled separately in Task 26 — skipped here.

    print("\n=== (6/7) Keepalive ===")
    print(t("wizard.keepalive.warning"))
    answers["keepalive_enabled"] = ask_yes_no("Enable keepalive?", default=False)
    if answers["keepalive_enabled"]:
        idx = ask_choice("Strategy:", ["polling (default)", "seamless (advanced)"], default=0)
        answers["keepalive_strategy"] = "polling" if idx == 0 else "seamless"

    print("\n=== (7/7) Schedule install ===")
    sched_idx = ask_choice(
        "Install scheduler:",
        ["LaunchAgent (recommended)", "Print crontab line only", "Skip"],
        default=0,
    )
    answers["schedule"] = ["launchagent", "crontab", "skip"][sched_idx]
    return answers


def _print_crontab_line() -> None:
    py = sys.executable
    print(f"\nAdd to your crontab:\n  */5 * * * * {py} -m quota_monitor run >> ~/.quota-monitor/quota-monitor.log 2>&1\n")


def _install_launchagent(*, data_dir: Path) -> None:
    from ..platform.schedule import generate_launch_agent_plist, install_launch_agent
    from ..platform.paths import launch_agent_path
    label = "io.github.frank.quotamonitor"
    plist = generate_launch_agent_plist(
        label=label,
        program_arguments=[sys.executable, "-m", "quota_monitor", "run"],
        interval_seconds=300,
        stdout_log=data_dir / "quota-monitor.log",
        stderr_log=data_dir / "quota-monitor.err.log",
    )
    install_launch_agent(plist_path=launch_agent_path(label), plist_content=plist)


def run_wizard(
    *,
    answers: Optional[dict] = None,
    config_path: Path,
    env_path: Path,
    data_dir: Path,
    non_interactive: bool = False,
) -> int:
    print("\n╔══════════════════════════════════╗")
    print("║   QuotaMonitor Setup Wizard     ║")
    print("╚══════════════════════════════════╝\n")

    errors, warnings = preflight_check(need_wrangler=False)
    for w in warnings:
        print(f"[warn] {w}")
    if errors:
        print("\n[error] preflight checks failed:")
        for e in errors:
            print(f"  - {e}")
        print("\nFix prerequisites and re-run (see README §Setup with your AI Agent).")
        return 2

    if not non_interactive:
        answers = _collect_interactive_answers()
    if answers is None:
        print("[error] no answers provided", file=sys.stderr)
        return 2

    data_dir.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.parent.mkdir(parents=True, exist_ok=True)

    config_path.write_text(_render_config(answers))
    env_path.write_text(_render_env(answers))
    print(f"\nWrote {config_path}\nWrote {env_path}")

    schedule = answers.get("schedule", "skip")
    if schedule == "launchagent":
        _install_launchagent(data_dir=data_dir)
        print("LaunchAgent installed.")
    elif schedule == "crontab":
        _print_crontab_line()

    set_locale(answers.get("locale", "en"))
    print(t("wizard.complete"))
    return 0
```

- [ ] **Step 7: Wire `__main__.py`** — add branch:

```python
    if args.cmd == "setup":
        from .cli.setup import run_wizard
        return run_wizard(
            config_path=platform_paths.config_file(),
            env_path=platform_paths.env_file(),
            data_dir=platform_paths.user_data_dir(),
        )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_wizard_smoke.py -v`
Expected: PASS (3 tests).

- [ ] **Step 9: Commit**

```bash
git add quota_monitor/cli/_input.py quota_monitor/cli/_preflight.py quota_monitor/cli/setup.py quota_monitor/__main__.py tests/test_wizard_smoke.py tests/fixtures/wizard_answers_basic.json
git commit -m "feat(cli): setup wizard with preflight + non-interactive smoke mode"
```

---

## Task 26: `cli/setup.py` step 5 — Cloudflare relay deployment

**Files:**
- Create: `quota_monitor/cli/_wrangler.py`
- Modify: `quota_monitor/cli/setup.py` (call CF step when primary == "cloudflare_relay")
- Test: `tests/test_wizard_cf.py`

- [ ] **Step 1: Write failing test**

`tests/test_wizard_cf.py`:
```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from quota_monitor.cli._wrangler import deploy_cf_relay


def _ok(stdout=""):
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def test_deploy_creates_kv_pushes_secrets_and_deploys(tmp_path):
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    (relay_dir / "wrangler.toml.example").write_text(
        'name = "qm-relay"\nmain = "src/worker.js"\n[[kv_namespaces]]\nbinding = "ALERTS_KV"\nid = "REPLACE_ME"\n'
    )
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["wrangler", "kv:namespace", "create"]:
            return _ok(stdout='{"id": "abc-kv-id"}\n')
        if cmd[:2] == ["wrangler", "deploy"]:
            return _ok(stdout='Published https://qm-relay-frank.workers.dev\n')
        return _ok()

    with patch("quota_monitor.cli._wrangler.subprocess.run", side_effect=fake_run):
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )
    assert url == "https://qm-relay-frank.workers.dev"
    # wrangler.toml should be written with the real KV id substituted in.
    toml = (relay_dir / "wrangler.toml").read_text()
    assert "abc-kv-id" in toml
    assert "REPLACE_ME" not in toml
    # Secrets were pushed.
    secret_cmds = [c for c in calls if c[:3] == ["wrangler", "secret", "put"]]
    assert any("TELEGRAM_BOT_TOKEN" in c for c in secret_cmds)
    assert any("TELEGRAM_CHAT_ID" in c for c in secret_cmds)


def test_deploy_returns_none_on_wrangler_failure(tmp_path):
    relay_dir = tmp_path / "cloudflare-relay"
    relay_dir.mkdir()
    (relay_dir / "wrangler.toml.example").write_text("[[kv_namespaces]]\nbinding=\"ALERTS_KV\"\nid=\"REPLACE_ME\"\n")
    fail = MagicMock(returncode=1, stdout="", stderr="boom")
    with patch("quota_monitor.cli._wrangler.subprocess.run", return_value=fail):
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token="TOK", telegram_chat_id="CID",
        )
    assert url is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_wizard_cf.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write `quota_monitor/cli/_wrangler.py`**

```python
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _run_wrangler(args: list[str], *, stdin: Optional[str] = None) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["wrangler", *args],
            input=stdin,
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "wrangler not found in PATH"


def deploy_cf_relay(
    *,
    relay_dir: Path,
    telegram_bot_token: str,
    telegram_chat_id: str,
) -> Optional[str]:
    """Half-automatic CF deploy. Returns the deployed worker URL on success, None on failure."""
    print("Creating KV namespace ALERTS_KV...")
    rc, out, err = _run_wrangler(["kv:namespace", "create", "ALERTS_KV"])
    if rc != 0:
        print(f"[error] kv:namespace create failed: {err}", file=sys.stderr)
        return None
    # Wrangler prints either JSON or a human line containing `id = "..."`. Try both.
    kv_id = None
    try:
        kv_id = json.loads(out).get("id")
    except json.JSONDecodeError:
        m = re.search(r'id\s*=\s*"([^"]+)"', out)
        if m:
            kv_id = m.group(1)
    if not kv_id:
        print(f"[error] could not parse KV id from wrangler output:\n{out}", file=sys.stderr)
        return None

    print(f"  KV id = {kv_id}")
    template = (relay_dir / "wrangler.toml.example").read_text()
    toml = template.replace("REPLACE_ME", kv_id)
    (relay_dir / "wrangler.toml").write_text(toml)

    print("Pushing secrets to Cloudflare...")
    for secret_name, secret_value in [
        ("TELEGRAM_BOT_TOKEN", telegram_bot_token),
        ("TELEGRAM_CHAT_ID", telegram_chat_id),
    ]:
        rc, _, err = _run_wrangler(["secret", "put", secret_name], stdin=secret_value + "\n")
        if rc != 0:
            print(f"[error] secret put {secret_name} failed: {err}", file=sys.stderr)
            return None

    print("Deploying worker...")
    rc, out, err = _run_wrangler(["deploy"])
    if rc != 0:
        print(f"[error] wrangler deploy failed: {err}", file=sys.stderr)
        return None
    m = re.search(r"https://[A-Za-z0-9.-]+\.workers\.dev[^\s]*", out)
    if not m:
        print(f"[error] could not parse deploy URL from output:\n{out}", file=sys.stderr)
        return None
    return m.group(0)
```

- [ ] **Step 4: Wire CF deployment into `setup.py`**

In `_collect_interactive_answers`, after step 4 (Telegram), add:

```python
    # === (5/7) Cloudflare relay deployment (only if user picked it) ===
    if answers["primary"] == "cloudflare_relay":
        print("\n=== (5/7) Cloudflare relay deployment ===")
        errors, _ = preflight_check(need_wrangler=True)
        if errors:
            print("[error] CF preflight failed:")
            for e in errors:
                print(f"  - {e}")
            print("Fix and re-run setup.")
            raise SystemExit(2)
        from ._wrangler import deploy_cf_relay
        from pathlib import Path
        relay_dir = Path(__file__).resolve().parent.parent.parent / "cloudflare-relay"
        url = deploy_cf_relay(
            relay_dir=relay_dir,
            telegram_bot_token=answers["telegram_bot_token"],
            telegram_chat_id=answers["telegram_chat_id"],
        )
        if url is None:
            print("[error] Cloudflare deploy failed. Re-run setup once you fix the issue.")
            raise SystemExit(3)
        answers["cloudflare_enabled"] = True
        answers["cloudflare_webhook_url"] = f"{url}/api/schedule"
        print(f"Deployed: {url}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_wizard_cf.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add quota_monitor/cli/_wrangler.py quota_monitor/cli/setup.py tests/test_wizard_cf.py
git commit -m "feat(cli): CF relay deploy step in wizard via wrangler subprocess"
```

---

## Task 27: `cloudflare-relay/` rebuild

**Files:**
- Create: `cloudflare-relay/README.md`
- Create: `cloudflare-relay/package.json`
- Create: `cloudflare-relay/wrangler.toml.example`
- Create: `cloudflare-relay/src/worker.js`

No automated tests (manual smoke via `wrangler dev`). The Worker logic is a 1:1 refactor of original `claude_status.js` with secrets moved to `env.TELEGRAM_BOT_TOKEN` / `env.TELEGRAM_CHAT_ID` instead of hardcoded constants.

- [ ] **Step 1: Create `cloudflare-relay/package.json`**

```json
{
  "name": "quota-monitor-relay",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "wrangler dev",
    "deploy": "wrangler deploy",
    "tail": "wrangler tail"
  },
  "devDependencies": {
    "wrangler": "^3.78.0"
  }
}
```

- [ ] **Step 2: Create `cloudflare-relay/wrangler.toml.example`**

```toml
name = "quota-monitor-relay"
main = "src/worker.js"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "ALERTS_KV"
id = "REPLACE_ME"

[triggers]
crons = ["*/3 * * * *"]
```

- [ ] **Step 3: Create `cloudflare-relay/src/worker.js`**

```javascript
// QuotaMonitor relay worker — schedules delayed Telegram alerts via KV.
// Secrets (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) come from `wrangler secret`,
// never hardcoded.

function handleClaudeStatus(payload) {
  if (payload.incident) {
    const icon = payload.incident.status === "resolved" ? "✅" : "🚨";
    return [
      `${icon} *Claude incident update*`,
      "",
      `*Event*: ${payload.incident.name}`,
      `*Status*: ${payload.incident.status}`,
      `*Detail*: ${payload.incident.incident_updates?.[0]?.body || "n/a"}`,
      `*Link*: ${payload.page?.url || "https://status.claude.com"}/incidents/${payload.incident.id}`,
    ].join("\n");
  }
  if (payload.component_update) {
    return [
      "⚠️ *Claude component status change*",
      "",
      `*Component*: ${payload.component.name}`,
      `*New status*: ${payload.component_update.new_status || payload.component.status}`,
    ].join("\n");
  }
  return null;
}

async function sendTelegram(env, text) {
  const url = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text, parse_mode: "Markdown" }),
  });
  if (!resp.ok) {
    console.log("Telegram error:", await resp.text());
    return new Response("telegram error", { status: 502 });
  }
  return new Response("ok", { status: 200 });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/api/schedule" && request.method === "POST") {
      try {
        const data = await request.json();
        const resetTime = data.reset_time_epoch || Math.floor(Date.now() / 1000);
        const key = `${resetTime}_${Math.random().toString(36).substring(2, 8)}`;
        await env.ALERTS_KV.put(key, JSON.stringify({ message: data.message || "Quota reset" }));
        return new Response("scheduled", { status: 200 });
      } catch (e) {
        return new Response(`schedule error: ${e.message}`, { status: 500 });
      }
    }

    if (request.method !== "POST") {
      return new Response("QuotaMonitor relay is alive.", { status: 200 });
    }

    let payload = {};
    try { payload = JSON.parse(await request.text()); }
    catch { return new Response("bad json", { status: 400 }); }

    const handlers = [handleClaudeStatus];
    let text = null;
    for (const h of handlers) { text = h(payload); if (text) break; }
    if (!text) {
      const safe = JSON.stringify(payload, null, 2).substring(0, 3000);
      text = `ℹ️ *Unhandled webhook*\n\n\`\`\`json\n${safe}\n\`\`\``;
    }
    return await sendTelegram(env, text);
  },

  async scheduled(event, env, ctx) {
    if (!env.ALERTS_KV) return;
    const now = Math.floor(Date.now() / 1000);
    const list = await env.ALERTS_KV.list();
    for (const key of list.keys) {
      const targetTime = parseInt(key.name.split("_")[0], 10);
      if (now < targetTime) continue;
      const raw = await env.ALERTS_KV.get(key.name);
      if (!raw) { await env.ALERTS_KV.delete(key.name); continue; }
      try {
        const data = JSON.parse(raw);
        const resp = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text: data.message, parse_mode: "Markdown" }),
        });
        if (resp.ok) await env.ALERTS_KV.delete(key.name);
        else console.log("scheduled telegram error:", await resp.text());
      } catch (e) {
        console.log("scheduled parse/network error:", e);
      }
    }
  },
};
```

- [ ] **Step 4: Create `cloudflare-relay/README.md`**

```markdown
# QuotaMonitor — Cloudflare relay

Deployable Worker that receives schedule POSTs from the local CLI and fires
Telegram messages on time. Free tier covers 100k req/day and 100k KV ops/day.

## Deploy

The `quota-monitor setup` wizard handles this for you. To deploy manually:

```bash
npm install -g wrangler
wrangler login
wrangler kv:namespace create ALERTS_KV     # copy the id into wrangler.toml
cp wrangler.toml.example wrangler.toml      # paste the kv id
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put TELEGRAM_CHAT_ID
wrangler deploy
```

The deployed URL goes into `~/.quota-monitor/config.toml`:

```toml
[notifiers.cloudflare_relay]
enabled = true
webhook_url = "https://<your-worker>.workers.dev/api/schedule"
```

## Security

Use a **scoped Cloudflare API token** (Workers + KV only) — never your
Global API Key. Revoke after deploy if you used an AI agent to assist.
```

- [ ] **Step 5: Commit**

```bash
git add cloudflare-relay/
git commit -m "feat(cf-relay): refactored worker with secrets via wrangler secret"
```

---

## Task 28: `README.md` (English, root)

**Files:**
- Create: `README.md`

No automated tests; manual review only.

- [ ] **Step 1: Write `README.md`**

Use the structure from spec §11 (Setup with your AI Agent / Quickstart / What it does / How it works / Safety & privacy / Cost / Choose your notification channel / Adding a channel / Advanced: CF relay / Risks / Platform support / Troubleshooting / Architecture / License).

Required content blocks (transcribe **verbatim** — these are the agreed surface):

**Header tagline**: `Monitor Claude / Codex 5-hour quota windows and notify on reset. Zero-dependency Python, optional Cloudflare relay.`

**§ Setup with your AI Agent — Step 1 prompt block** (exact text from spec §11.2 Step 1).

**§ Risks** sections (exact text from spec §11.4):
- Keepalive (auto-renew Claude 5h window): default off, ToS, sleep limitation, workarounds.
- Keepalive content randomization — what it does and doesn't.
- Secret leak.

**§ How it works** (exact text from spec §11 "How it works (in 30 seconds)").

**§ Safety & privacy** (exact text from spec §11 "Safety & privacy").

**§ Cost** (exact text from spec §11 "Cost").

- [ ] **Step 2: Manual review**

Read the rendered Markdown. Verify:
- All anchor links resolve.
- No real secrets ever appear.
- Every section listed in spec §11.1 exists.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README (English) with AI agent prep prompt"
```

---

## Task 29: `README.zh-CN.md` (Chinese, root)

**Files:**
- Create: `README.zh-CN.md`

- [ ] **Step 1: Write `README.zh-CN.md`**

Translate `README.md` section-by-section. Section headings, ordering, and code blocks (including the AI agent prep prompt) must match. The prompt itself stays English (user pastes to their English-speaking agent).

Top of file:
```markdown
> English | [简体中文](#)

[切换语言: [English](README.md) | 中文]
```

- [ ] **Step 2: Cross-check parity**

Manually diff section headings between `README.md` and `README.zh-CN.md` — they must be 1:1.

- [ ] **Step 3: Commit**

```bash
git add README.zh-CN.md
git commit -m "docs: README simplified Chinese translation"
```

---

## Task 30: `docs/` subdocs

**Files:**
- Create: `docs/ARCHITECTURE.md`
- Create: `docs/cloudflare.md`
- Create: `docs/adding-notifier.md`
- Create: `docs/linux-systemd.md`

- [ ] **Step 1: `docs/ARCHITECTURE.md`**

Content: re-organize spec §3 (module boundaries table + directory structure + data flow). Add the Full Replay state-flow note from Task 9.

- [ ] **Step 2: `docs/cloudflare.md`**

Content: full CF deploy walkthrough (auto via wizard / manual / secret rotation / debug `wrangler tail` / cost math).

- [ ] **Step 3: `docs/adding-notifier.md`**

Content: contributor guide. Show:
1. `Notifier` Protocol signature (copy from `notifiers/__init__.py`).
2. Implement a class with `name: str` + `send(self, alert: Alert) -> None`.
3. Wire it into `cli/run.py` `_build_notifier()` and `cli/notify_test.py`.
4. Add a contract test in `tests/test_notifier_<name>.py` following the Telegram pattern.
5. Add the option to `cli/setup.py` step 3.

- [ ] **Step 4: `docs/linux-systemd.md`**

Content: example systemd timer + service unit for Linux users.

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

Enable: `systemctl --user enable --now quota-monitor.timer`

- [ ] **Step 5: Commit**

```bash
git add docs/ARCHITECTURE.md docs/cloudflare.md docs/adding-notifier.md docs/linux-systemd.md
git commit -m "docs: architecture, cloudflare guide, notifier authoring, linux systemd"
```

---

## Task 31: meta files — `config.example.toml` / `.env.example` / `LICENSE` / `CONTRIBUTING.md`

**Files:**
- Create: `config.example.toml`
- Create: `.env.example`
- Create: `LICENSE`
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: `config.example.toml`** — same content as spec §5.1 (the full TOML schema with comments).

- [ ] **Step 2: `.env.example`**

```dotenv
# QuotaMonitor secrets — copy to ~/.quota-monitor/.env and fill in
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

- [ ] **Step 3: `LICENSE`** — MIT license text with author "Frank" and year 2026.

- [ ] **Step 4: `CONTRIBUTING.md`**

```markdown
# Contributing to QuotaMonitor

## Setup

```bash
python3.11 -m pip install --user pytest
python3 -m pytest -v
```

## Conventions

- **Conventional commits**: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.
- **One commit per task** in `docs/superpowers/plans/`.
- **TDD**: red → green → refactor. No untested code in `quota_monitor/`.
- **Zero runtime dependencies**: stdlib only. Dev deps go in `[project.optional-dependencies] dev`.

## i18n

Whenever you edit `README.md`, update `README.zh-CN.md` to match section-by-section.

Whenever you add an `i18n.t(key)` call, add the key to BOTH `quota_monitor/i18n/messages/en.py` and `zh.py`.

## Pre-commit

Run before pushing:
```bash
python3 -m pytest -v
```
```

- [ ] **Step 5: Commit**

```bash
git add config.example.toml .env.example LICENSE CONTRIBUTING.md
git commit -m "chore: example config, env template, MIT license, contributing guide"
```

---

## Task 32: v1 acceptance checklist

**Files:**
- Create: `docs/superpowers/plans/2026-05-16-acceptance-results.md`

This task is the **release gate**. Run each criterion from spec §14 manually and record pass/fail/blocker.

- [ ] **Step 1: Run automated tests**

```bash
python3 -m pytest -v
```
Expected: all green. Record total test count.

- [ ] **Step 2: Run each acceptance criterion**

For each criterion in spec §14, run it on a clean macOS user account (or VM):

```
[ ] Fresh macOS, no dotfiles → `setup` → first test notification within 5 min via Telegram
[ ] Fresh macOS + CF picked → wrangler deploy succeeds, webhook_url written
[ ] Inject 5-turn jsonl fixture → `run --dry-run` reports "would alert at <reset_time>"
[ ] `run` twice in same window → first sends, second is silent
[ ] keepalive=true + idle 5h → `claude -p <random phrase>` actually runs (verify log)
[ ] Delete a config field → `run` exits non-zero with a clear message
[ ] Corrupt state.json → `run` self-heals + emits warn log
[ ] LaunchAgent + reboot Mac → cron triggers within 5 min
[ ] AI Agent prep prompt to Claude Code → agent completes prep unaided
[ ] `notify-test` succeeds for each enabled backend
[ ] phrase pool over 11 keepalives → first 10 unique, 11th starts new round
[ ] README.md / README.zh-CN.md section parity (manual diff)
```

- [ ] **Step 3: Write `docs/superpowers/plans/2026-05-16-acceptance-results.md`**

Record each criterion's outcome (pass / fail / blocker + workaround). Open issues for any blocker.

- [ ] **Step 4: Tag release**

If all criteria pass:
```bash
git tag -a v0.1.0 -m "v0.1.0 — first open-source release"
```

- [ ] **Step 5: Commit acceptance results**

```bash
git add docs/superpowers/plans/2026-05-16-acceptance-results.md
git commit -m "chore(release): v0.1.0 acceptance results"
```

---

## Self-Review Notes

After writing the full plan, the author re-checked it against the spec and applied these fixes:

1. **Bug regression integrated (Tasks 4 / 9 / 18 / 19 / 21 / 22)**: original `monitor.py` had a state-feedback bug where a future-dated saved reset silenced alerts. Tasks 4 and 9 redesign around **Full Replay** — `replay_windows(timestamps)` takes no state, so the failure mode is structurally impossible. State JSON keeps only `alerted_for_reset`. Tasks 18/19 (keepalive) compute their window inline via `replay_windows` rather than reading state. Task 22 (status) similarly stops referencing window-start/reset fields that no longer exist.

2. **Spec §6 updated** to reflect the simplified state schema (single `alerted_for_reset` field for Claude).

3. **Type consistency check**: `AlertDecision` signature unchanged; `LatestWindow` is new (Task 9) and consumed by `decide_alerts`, `polling_tick`, `seamless_tick`, and `run_once`.

4. **Placeholder scan**: no TBDs or vague instructions remain. Every step has either complete code or a verbatim file content. Task 28 (English README) references spec §11 verbatim content — that's fine because the spec is the source.

5. **Spec coverage**: every requirement in spec §3-§14 maps to at least one task (T1-T32).

