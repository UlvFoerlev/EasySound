import copy

from actions.legacy_action import migrate_action_ids

OLD = "dev_core477_EasySound::PlaySound"
NEW = "uf_easy_sound::PlaySound"


def page(*action_ids):
    return {
        "keys": {
            "0x0": {
                "states": {
                    "0": {
                        "actions": [
                            {"id": action_id, "settings": {"filepath": "/tmp/a.wav"}}
                            for action_id in action_ids
                        ]
                    }
                }
            }
        }
    }


def test_rewrites_a_legacy_action():
    data = page(OLD)
    assert migrate_action_ids(data, OLD, NEW) == 1
    assert data["keys"]["0x0"]["states"]["0"]["actions"][0]["id"] == NEW


def test_preserves_action_settings():
    data = page(OLD)
    migrate_action_ids(data, OLD, NEW)
    action = data["keys"]["0x0"]["states"]["0"]["actions"][0]
    assert action["settings"] == {"filepath": "/tmp/a.wav"}


def test_leaves_other_plugins_alone():
    data = page("com_core447_OSPlugin::Delay", OLD)
    assert migrate_action_ids(data, OLD, NEW) == 1
    ids = [a["id"] for a in data["keys"]["0x0"]["states"]["0"]["actions"]]
    assert ids == ["com_core447_OSPlugin::Delay", NEW]


def test_counts_every_occurrence():
    data = {"a": page(OLD, OLD), "b": page(OLD)}
    assert migrate_action_ids(data, OLD, NEW) == 3


def test_is_idempotent():
    data = page(OLD)
    migrate_action_ids(data, OLD, NEW)
    assert migrate_action_ids(data, OLD, NEW) == 0


def test_reports_nothing_for_a_clean_page():
    data = page(NEW)
    before = copy.deepcopy(data)
    assert migrate_action_ids(data, OLD, NEW) == 0
    assert data == before


def test_handles_odd_shapes():
    assert migrate_action_ids(None, OLD, NEW) == 0
    assert migrate_action_ids([], OLD, NEW) == 0
    assert migrate_action_ids({"id": None}, OLD, NEW) == 0
    assert migrate_action_ids("a string", OLD, NEW) == 0


def test_does_not_touch_a_matching_string_elsewhere():
    # Only a dict's "id" key is rewritten, so a comment mentioning the old id is left alone
    data = {"keys": {"0x0": {"comment": OLD}}}
    assert migrate_action_ids(data, OLD, NEW) == 0
    assert data["keys"]["0x0"]["comment"] == OLD
