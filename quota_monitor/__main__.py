import argparse
import sys
import time


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quota_monitor")
    parser.add_argument("--version", action="version", version="quota_monitor 0.2.1")
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

    from .platform import paths as platform_paths

    if args.cmd == "run":
        from .cli.run import run_once
        return run_once(
            config_path=platform_paths.config_file(),
            env_path=platform_paths.env_file(),
            state_path=platform_paths.state_file(),
            now=time.time(),
            dry_run=args.dry_run,
        )
    if args.cmd == "status":
        from .cli.status import show_status
        return show_status(
            state_path=platform_paths.state_file(),
            config_path=platform_paths.config_file(),
        )
    if args.cmd == "notify-test":
        from .cli.notify_test import send_test
        return send_test(
            config_path=platform_paths.config_file(),
            env_path=platform_paths.env_file(),
            backend=args.backend,
        )
    if args.cmd == "uninstall":
        from .cli.uninstall import uninstall
        label = "io.github.frank.quotamonitor"
        return uninstall(
            launch_agent_label=label,
            plist_path=platform_paths.launch_agent_path(label),
        )
    if args.cmd == "setup":
        from .cli.setup import run_wizard
        return run_wizard(
            config_path=platform_paths.config_file(),
            env_path=platform_paths.env_file(),
            data_dir=platform_paths.user_data_dir(),
        )
    # other subcommands wired in later tasks
    print(f"[stub] {args.cmd} not yet implemented", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
