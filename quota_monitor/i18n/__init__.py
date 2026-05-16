from .messages import en, zh

_TABLES = {"en": en.MESSAGES, "zh": zh.MESSAGES}
_current_locale = "en"


def set_locale(locale: str) -> None:
    global _current_locale
    if locale not in _TABLES:
        raise ValueError(f"unsupported locale: {locale}. Supported: {list(_TABLES)}")
    _current_locale = locale


def t(key: str, **kwargs) -> str:
    table = _TABLES[_current_locale]
    template = table.get(key)
    if template is None:
        return f"[missing i18n key: {key}]"
    try:
        return template.format(**kwargs)
    except KeyError as e:
        return f"[i18n format error in {key}: missing {e}]"
