# Import StreamController modules
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.PluginManager.PluginBase import PluginBase
import json
import shutil
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk

import globals as gl

from .actions.legacy_action import action_id_in_pages, migrate_action_ids
from .actions.play_sound.play_sound import PlaySoundAction

# Wiki
# https://streamcontroller.github.io/docs/latest/

# v1 typo'd Core447's own prefix (dev_core477 vs dev_core447); kept registered for backwards compatibility
LEGACY_PLAY_SOUND_ACTION_ID = "dev_core477_EasySound::PlaySound"

LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"
LOGO_SOURCE_HEIGHT = 64


def logo_image() -> Gtk.Image:
    """A fresh logo widget; each holder needs its own, since the chooser reparents the one it is given."""
    # No size request on purpose: every other plugin's prefix measures 16x16, and a wider one indents
    # both the icon and the title out of line with the rest of the list. The source is loaded larger
    # than the icon box so it stays sharp when GTK scales it down.
    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(LOGO_PATH), -1, LOGO_SOURCE_HEIGHT, True)

    return Gtk.Image.new_from_pixbuf(pixbuf)


class PluginEasySound(PluginBase):
    def __init__(self):
        super().__init__()

        self.lm = self.locale_manager

        self.setup_backend()
        # Kept: setup_actions needs to know a migration happened, since it erases its own evidence
        self.migrated_pages = self.migrate_legacy_pages()
        self.setup_actions()

        # Register plugin
        self.register(
            plugin_name="EasySound",
            github_repo="https://github.com/UlvFoerlev/EasySound",
            plugin_version="2.0.0",
            app_version="1.5.0-beta.15",
        )

    def setup_actions(self):
        action_support = {
            Input.Key: ActionInputSupport.SUPPORTED,
            Input.Dial: ActionInputSupport.UNTESTED,
            Input.Touchscreen: ActionInputSupport.UNSUPPORTED,
        }

        self.action_play_sound = ActionHolder(
            plugin_base=self,
            action_core=PlaySoundAction,
            action_id_suffix="PlaySound",
            action_name=self.lm.get("action.play-sound.name"),
            action_support=action_support,
            icon=logo_image(),
        )
        self.add_action_holder(self.action_play_sound)

        # Registered only when in use: every registered holder gets a row in the action chooser, unconditionally
        if not self.migrated_pages and not self.legacy_action_in_use():
            return

        # Only a safety net for pages already read into memory this session; it retires itself once
        # migrate_legacy_pages has rewritten every page, because then no page mentions the old id
        self.action_play_sound_legacy = ActionHolder(
            plugin_base=self,
            action_core=PlaySoundAction,
            action_id=LEGACY_PLAY_SOUND_ACTION_ID,
            action_name=self.lm.get("action.play-sound.name-legacy"),
            action_support=action_support,
            description=self.lm.get("action.play-sound.description-legacy"),
            icon=logo_image(),
        )
        self.add_action_holder(self.action_play_sound_legacy)

    def get_selector_icon(self) -> Gtk.Widget:
        return logo_image()

    def play_sound_action_id(self) -> str:
        return f"{self.get_plugin_id()}::PlaySound"

    def migrate_legacy_pages(self) -> int:
        """Rewrites the v1 action id in saved pages so the legacy holder can eventually be deleted."""
        try:
            page_paths = gl.page_manager.get_pages()
        except Exception:
            return 0

        migrated = 0
        for page_path in page_paths:
            try:
                migrated += self.migrate_page(Path(page_path))
            except Exception:  # one unwritable page must not stop the rest
                continue

        return migrated

    def migrate_page(self, page_path: Path) -> int:
        try:
            data = json.loads(page_path.read_text())
        except (OSError, ValueError):
            return 0

        changed = migrate_action_ids(
            data, LEGACY_PLAY_SOUND_ACTION_ID, self.play_sound_action_id()
        )
        if not changed:
            return 0

        # The original goes outside the pages directory, where it cannot be picked up as a page itself
        backup_dir = Path(gl.DATA_PATH) / "easysound-v1-page-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / page_path.name
        if not backup.exists():
            shutil.copy2(page_path, backup)

        page_path.write_text(json.dumps(data, indent=4) + "\n")
        return changed

    def legacy_action_in_use(self) -> bool:
        # Fails open when the page list is unavailable, for the same reason action_id_in_pages does
        try:
            page_paths = gl.page_manager.get_pages()
        except Exception:
            return True

        return action_id_in_pages(LEGACY_PLAY_SOUND_ACTION_ID, page_paths)

    def setup_backend(self):
        # Launch backend
        backend_path = Path(__file__).parent / "actions" / "backend.py"
        venv_path = Path(__file__).parent / ".venv"

        self.launch_backend(
            backend_path=backend_path, open_in_terminal=False, venv_path=venv_path
        )
        self.wait_for_backend()
