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
