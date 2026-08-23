import pytest

from actions.audio_targets import (
    ICON_ALL,
    ICON_BLUETOOTH,
    ICON_CUSTOM,
    ICON_DEFAULT,
    ICON_GROUP,
    ICON_HEADSET,
    ICON_SPEAKER,
    Target,
    find_group,
    format_group_target,
    format_sink_target,
    missing_sinks,
    normalize_groups,
    resolve_target,
    sink_icon,
    target_icon,
)

SINK_A = "alsa_output.pci-0000_64_00.6.analog-stereo"
SINK_B = "bluez_output.AC_12_2F_98_71_0B.1"
GROUPS = [{"id": "g1", "name": "Living room", "sinks": [SINK_A, SINK_B]}]


# target, sinks present right now, groups, expected resolution
RESOLVE_CASES = [
    ("default", Target.DEFAULT, [SINK_A], None, None),
    ("empty", "", [SINK_A], None, None),
    # "Custom..." only opens the editor, so it must behave as default rather than as a target
    ("custom", Target.CUSTOM, [SINK_A], None, None),
    ("unknown shape", "nonsense", [SINK_A], None, None),
    ("all", Target.ALL, [SINK_A, SINK_B], None, [SINK_A, SINK_B]),
    ("one sink", format_sink_target(SINK_A), [SINK_A, SINK_B], None, [SINK_A]),
    ("absent sink", format_sink_target(SINK_B), [SINK_A], None, []),
    # Losing one speaker must not take the whole group down
    ("group missing a member", format_group_target("g1"), [SINK_A], GROUPS, [SINK_A]),
    ("group with none present", format_group_target("g1"), [], GROUPS, []),
    ("group keeps its order", format_group_target("g1"), [SINK_B, SINK_A], GROUPS, [SINK_A, SINK_B]),
    ("deleted group", format_group_target("gone"), [SINK_A], GROUPS, []),
]


@pytest.mark.parametrize(
    "target,present,groups,expected",
    [case[1:] for case in RESOLVE_CASES],
    ids=[case[0] for case in RESOLVE_CASES],
)
def test_resolve_target(target, present, groups, expected):
    resolved = resolve_target(target, present, groups)

    # None and [] are different answers: one lets the server choose, the other plays nowhere
    if expected is None:
        assert resolved is None
    else:
        assert resolved == expected


def test_missing_sinks_reports_absent_members():
    assert missing_sinks(format_group_target("g1"), [SINK_A], GROUPS) == [SINK_B]
    assert missing_sinks(format_sink_target(SINK_B), [SINK_A]) == [SINK_B]
    assert missing_sinks(Target.DEFAULT, []) == []


def test_find_group():
    assert find_group(GROUPS, "g1")["name"] == "Living room"
    assert find_group(GROUPS, "nope") is None


def test_normalize_drops_malformed_entries():
    raw = [
        {"id": "ok", "name": "Fine", "sinks": [SINK_A, 5, None, ""]},
        {"id": "", "name": "No id", "sinks": []},
        {"id": "x", "name": "   ", "sinks": []},
        {"id": "y", "name": "No sinks key"},
        {"name": "id missing", "sinks": []},
        "not a dict",
        None,
    ]
    assert normalize_groups(raw) == [{"id": "ok", "name": "Fine", "sinks": [SINK_A]}]


def test_normalize_handles_non_list():
    assert normalize_groups(None) == []
    assert normalize_groups({"id": "x"}) == []
    assert normalize_groups("nope") == []


def test_normalize_strips_names():
    assert normalize_groups([{"id": "a", "name": "  Desk  ", "sinks": []}])[0]["name"] == "Desk"


def test_new_group_ids_are_unique():
    from actions.audio_targets import new_group_id

    assert new_group_id() != new_group_id()


def test_upsert_appends_then_replaces():
    from actions.audio_targets import upsert_group

    groups = upsert_group([], "g1", "Desk", [SINK_A])
    assert groups == [{"id": "g1", "name": "Desk", "sinks": [SINK_A]}]

    groups = upsert_group(groups, "g1", "Desk renamed", [SINK_B])
    assert groups == [{"id": "g1", "name": "Desk renamed", "sinks": [SINK_B]}]

    groups = upsert_group(groups, "g2", "Other", [])
    assert [g["id"] for g in groups] == ["g1", "g2"]


def test_upsert_does_not_mutate_the_input():
    from actions.audio_targets import upsert_group

    original = [{"id": "g1", "name": "Desk", "sinks": [SINK_A]}]
    upsert_group(original, "g1", "Changed", [])
    assert original == [{"id": "g1", "name": "Desk", "sinks": [SINK_A]}]


def test_delete_group_removes_only_that_group():
    from actions.audio_targets import delete_group

    groups = [{"id": "a", "name": "A", "sinks": []}, {"id": "b", "name": "B", "sinks": []}]
    assert [g["id"] for g in delete_group(groups, "a")] == ["b"]
    assert [g["id"] for g in delete_group(groups, "missing")] == ["a", "b"]


class FakeComboItem:
    """Stands in for SimpleComboRowItem, which ComboRow passes to on_change instead of the value."""

    def __init__(self, value):
        self._value = value

    def get_value(self):
        return self._value


def test_target_value_unwraps_combo_items():
    from actions.audio_targets import target_value

    assert target_value(FakeComboItem(Target.CUSTOM)) == Target.CUSTOM
    assert target_value(FakeComboItem(format_sink_target(SINK_A))) == format_sink_target(SINK_A)


def test_target_value_passes_plain_strings_through():
    from actions.audio_targets import target_value

    assert target_value(Target.DEFAULT) == Target.DEFAULT


def test_target_value_handles_missing_and_odd_values():
    from actions.audio_targets import target_value

    # get_item returns None when the old selection is no longer in the list
    assert target_value(None) == ""
    assert target_value(FakeComboItem(None)) == ""
    assert target_value(7) == ""


@pytest.mark.parametrize(
    "kind,bluetooth,expected",
    [
        ("speaker", False, ICON_SPEAKER),
        ("speaker", True, ICON_BLUETOOTH),
        ("headset", False, ICON_HEADSET),
        # A wireless headset is a headset first: that is the more useful thing to show
        ("headset", True, ICON_HEADSET),
    ],
)
def test_sink_icons_by_device_type(kind, bluetooth, expected):
    assert sink_icon(kind, bluetooth) == expected


def test_sink_icon_defaults_without_a_known_device():
    assert sink_icon() == ICON_SPEAKER


@pytest.mark.parametrize(
    "target,expected",
    [
        (Target.DEFAULT, ICON_DEFAULT),
        ("", ICON_DEFAULT),
        (Target.ALL, ICON_ALL),
        (Target.CUSTOM, ICON_CUSTOM),
        (format_group_target("g1"), ICON_GROUP),
        (format_sink_target(SINK_A), ICON_SPEAKER),
    ],
)
def test_target_icons(target, expected):
    assert target_icon(target) == expected
