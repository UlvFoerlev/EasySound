from collections.abc import Iterable
from pathlib import Path


def action_id_in_pages(action_id: str, page_paths: Iterable[str]) -> bool:
    # Fails open on an unreadable page: a hidden holder breaks pages, a needlessly shown one is cosmetic
    for page_path in page_paths:
        try:
            if action_id in Path(page_path).read_text():
                return True
        except OSError:
            return True

    return False


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
