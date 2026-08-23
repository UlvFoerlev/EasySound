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


IDS = {OLD, NEW}


def action(**settings):
    return {"keys": {"0x0": {"states": {"0": {"actions": [{"id": NEW, "settings": settings}]}}}}}


def settings_of(data):
    return data["keys"]["0x0"]["states"]["0"]["actions"][0]["settings"]


def test_a_single_filepath_becomes_a_sound_list():
    from actions.legacy_action import migrate_action_settings

    data = action(filepath="/s/a.wav", mode="Release")
    assert migrate_action_settings(data, IDS) == 1
    assert settings_of(data)["sounds"] == ["/s/a.wav"]


def test_the_original_settings_are_left_in_place():
    from actions.legacy_action import migrate_action_settings

    data = action(filepath="/s/a.wav", mode="Release", fade_out=0.5)
    migrate_action_settings(data, IDS)
    kept = settings_of(data)

    # Left untouched so a rollback still finds its sound
    assert kept["filepath"] == "/s/a.wav"
    assert kept["mode"] == "Release"
    assert kept["fade_out"] == 0.5


def test_extras_are_folded_in_after_the_primary():
    from actions.legacy_action import migrate_action_settings

    data = action(filepath="/s/a.wav", extra_filepaths=["/s/b.wav", "/s/c.wav"])
    migrate_action_settings(data, IDS)
    assert settings_of(data)["sounds"] == ["/s/a.wav", "/s/b.wav", "/s/c.wav"]


def test_an_existing_list_is_never_overwritten():
    from actions.legacy_action import migrate_action_settings

    data = action(filepath="/s/old.wav", sounds=["/s/chosen.wav"])
    assert migrate_action_settings(data, IDS) == 0
    assert settings_of(data)["sounds"] == ["/s/chosen.wav"]


def test_an_emptied_list_stays_empty():
    from actions.legacy_action import migrate_action_settings

    # The user deleted every sound; the old filepath must not come back
    data = action(filepath="/s/old.wav", sounds=[])
    assert migrate_action_settings(data, IDS) == 0
    assert settings_of(data)["sounds"] == []


def test_an_action_with_no_sound_is_skipped():
    from actions.legacy_action import migrate_action_settings

    data = action(mode="Press")
    assert migrate_action_settings(data, IDS) == 0
    assert "sounds" not in settings_of(data)


def test_other_plugins_are_untouched():
    from actions.legacy_action import migrate_action_settings

    data = {"actions": [{"id": "com_core447_OSPlugin::Delay", "settings": {"filepath": "/x"}}]}
    assert migrate_action_settings(data, IDS) == 0
    assert "sounds" not in data["actions"][0]["settings"]


def test_settings_migration_is_idempotent():
    from actions.legacy_action import migrate_action_settings

    data = action(filepath="/s/a.wav")
    migrate_action_settings(data, IDS)
    assert migrate_action_settings(data, IDS) == 0


def test_settings_migration_survives_odd_shapes():
    from actions.legacy_action import migrate_action_settings

    assert migrate_action_settings(None, IDS) == 0
    assert migrate_action_settings({"id": NEW, "settings": "not a dict"}, IDS) == 0
    assert migrate_action_settings({"id": NEW}, IDS) == 0
