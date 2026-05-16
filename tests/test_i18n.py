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
