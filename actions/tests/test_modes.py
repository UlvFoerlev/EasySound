from actions.modes import MODE_LOCALES, Mode


def test_every_mode_has_a_locale_key():
    assert set(MODE_LOCALES) == set(Mode)


def test_mode_locale_keys_exist(locales):
    missing = {mode: key for mode, key in MODE_LOCALES.items() if key not in locales}
    assert not missing


def test_mode_values_are_unique():
    values = [mode.value for mode in Mode]
    assert len(values) == len(set(values))


def test_declaration_order_is_the_dropdown_order():
    # The mode dropdown maps selection to mode by list index, so reordering silently remaps saved settings
    assert [mode.value for mode in Mode] == [
        "Press",
        "Release",
        "Hold",
        "Turn On",
        "Turn OFF",
        "Play until Turned Off",
    ]
