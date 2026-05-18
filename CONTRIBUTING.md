# Contributing to quota-monitor

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

## Releasing

See [docs/RELEASING.md](docs/RELEASING.md) for the full GitHub + PyPI + Homebrew release pipeline.
