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


def test_statusline_wizard_keys_exist_en():
    set_locale("en")
    assert "[missing" not in t("wizard.statusline.title", step="8/8")
    assert "[missing" not in t("wizard.statusline.enable_fresh")
    assert "[missing" not in t("wizard.statusline.enable_existing", cmd_preview="test")
    assert "[missing" not in t("wizard.statusline.already_configured")


def test_statusline_wizard_keys_exist_zh():
    set_locale("zh")
    assert "[missing" not in t("wizard.statusline.title", step="8/8")
    assert "[missing" not in t("wizard.statusline.enable_fresh")
    assert "[missing" not in t("wizard.statusline.enable_existing", cmd_preview="test")
    assert "[missing" not in t("wizard.statusline.already_configured")


def test_uninstall_statusline_keys():
    set_locale("en")
    assert "[missing" not in t("uninstall.statusline.restored")
    assert "[missing" not in t("uninstall.statusline.skipped_manual")
    assert "[missing" not in t("uninstall.statusline.verify_cmd")
    set_locale("zh")
    assert "[missing" not in t("uninstall.statusline.restored")
    assert "[missing" not in t("uninstall.statusline.skipped_manual")


def test_alert_suffix_keys():
    set_locale("en")
    assert "[missing" not in t("alert.suffix.estimated")
    set_locale("zh")
    assert "[missing" not in t("alert.suffix.estimated")
