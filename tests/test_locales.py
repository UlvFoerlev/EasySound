import re

from conftest import source_files

LM_GET = re.compile(r"lm\.get\(\s*\"([^\"]+)\"")
# Generative UI rows resolve title/subtitle/dialog_title through the locale manager themselves
ROW_LABEL = re.compile(r"(?:title|subtitle|dialog_title)=\"([^\"]+)\"")


def _looks_like_a_key(value: str) -> bool:
    return value.startswith("action.")


def _requested_keys() -> dict[str, list[str]]:
    requested = {}

    for path in source_files():
        text = path.read_text()
        keys = LM_GET.findall(text) + [
            value for value in ROW_LABEL.findall(text) if _looks_like_a_key(value)
        ]
        if keys:
            requested[path.name] = keys

    return requested


def test_every_requested_locale_key_exists(locales):
    missing = {
        name: [key for key in keys if key not in locales]
        for name, keys in _requested_keys().items()
    }

    assert not {name: keys for name, keys in missing.items() if keys}


def test_row_labels_are_keys_not_literal_text():
    # A row given literal text still renders, so only a locale-key convention keeps strings translatable
    literals = {}

    for path in source_files():
        for value in ROW_LABEL.findall(path.read_text()):
            if not _looks_like_a_key(value):
                literals.setdefault(path.name, []).append(value)

    assert not literals


def test_locale_values_are_non_empty_strings(locales):
    bad = {k: v for k, v in locales.items() if not isinstance(v, str) or not v.strip()}
    assert not bad
