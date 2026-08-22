import re

from conftest import source_files

LM_GET = re.compile(r"lm\.get\(\s*\"([^\"]+)\"")


def test_every_requested_locale_key_exists(locales):
    missing = {}

    for path in source_files():
        for key in LM_GET.findall(path.read_text()):
            if key not in locales:
                missing.setdefault(path.name, []).append(key)

    assert not missing


def test_locale_values_are_non_empty_strings(locales):
    bad = {k: v for k, v in locales.items() if not isinstance(v, str) or not v.strip()}
    assert not bad
