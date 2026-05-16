import argparse
import sys
import time


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
        from .platform import paths as platform_paths
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
