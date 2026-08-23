
from .playlist import normalize_paths



def migrate_action_ids(data, old_id: str, new_id: str) -> int:
    """Rewrites action ids in a loaded page, in place, and returns how many were changed."""
    changed = 0

    if isinstance(data, dict):
        # Page files only ever hold an action id at keys/<coord>/states/<n>/actions/[]/id
        if data.get("id") == old_id:
            data["id"] = new_id
            changed += 1

        for value in data.values():
            changed += migrate_action_ids(value, old_id, new_id)

    elif isinstance(data, list):
        for value in data:
            changed += migrate_action_ids(value, old_id, new_id)

    return changed


def migrate_action_settings(data, action_ids: set) -> int:
    """Gives each of our actions a "sounds" list, so the single-filepath settings can be retired."""
    changed = 0

    if isinstance(data, dict):
        settings = data.get("settings")
        if data.get("id") in action_ids and isinstance(settings, dict):
            # Only filled in when absent: a list the user has already edited is authoritative
            if "sounds" not in settings:
                sounds = normalize_paths(
                    settings.get("filepath"), settings.get("extra_filepaths")
                )
                if sounds:
                    settings["sounds"] = sounds
                    changed += 1

        for value in data.values():
            changed += migrate_action_settings(value, action_ids)

    elif isinstance(data, list):
        for value in data:
            changed += migrate_action_settings(value, action_ids)

    return changed

