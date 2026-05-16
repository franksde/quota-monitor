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
