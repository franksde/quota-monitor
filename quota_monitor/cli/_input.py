"""Tiny interactive input helpers — no third-party deps."""


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
