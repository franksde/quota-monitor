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
