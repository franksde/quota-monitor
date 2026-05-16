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
