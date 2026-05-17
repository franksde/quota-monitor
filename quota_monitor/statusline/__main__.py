import sys
from pathlib import Path


def main() -> int:
    from .wrapper import run_wrapper

    # Intentionally duplicated: statusline startup must avoid importing quota_monitor internals.
    data_dir = Path.home() / ".quota-monitor"
    return run_wrapper(
        cache_path=data_dir / "rate_limits_cache.json",
        original_path=data_dir / "statusline_original.json",
    )


if __name__ == "__main__":
    sys.exit(main())
