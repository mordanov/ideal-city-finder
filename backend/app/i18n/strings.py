"""
Backend i18n translation dictionary for user-facing strings.

Design decision (documented here per spec):
- Backend translates ONLY error/status messages and system labels.
- Criterion type identifiers (e.g. "poi_proximity") remain fixed English enum
  values in the JSON API and are NOT translated by the backend.
- Frontend translates all UI copy and criterion labels using the same criterion
  `type` values as keys in its own i18n dictionary.
- This avoids duplicating translation strings in two places.
- Proper nouns (city names, province names, user's free-text query) are never translated.
"""

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "invalid_credentials": "Invalid credentials",
        "token_expired": "Token has expired",
        "token_invalid": "Invalid authentication token",
        "not_authenticated": "Not authenticated",
        "run_not_found": "Search run not found",
        "status_pending": "Pending",
        "status_running": "Running",
        "status_done": "Done",
        "status_failed": "Failed",
        "data_unavailable": "Data unavailable for this city",
        "criterion_unsupported": "Unsupported criterion",
        "internal_error": "An internal error occurred",
    },
    "ru": {
        "invalid_credentials": "Неверные учётные данные",
        "token_expired": "Токен истёк",
        "token_invalid": "Недействительный токен авторизации",
        "not_authenticated": "Необходима авторизация",
        "run_not_found": "Поиск не найден",
        "status_pending": "Ожидание",
        "status_running": "Выполняется",
        "status_done": "Готово",
        "status_failed": "Ошибка",
        "data_unavailable": "Данные недоступны для этого города",
        "criterion_unsupported": "Неподдерживаемый критерий",
        "internal_error": "Произошла внутренняя ошибка",
    },
}


def t(key: str, language: str = "en") -> str:
    """Translate a key to the given language. Falls back to English if key/language missing."""
    return STRINGS.get(language, STRINGS["en"]).get(key, STRINGS["en"].get(key, key))
