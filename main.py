# Import StreamController modules
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionHolderGroup import ActionHolderGroup
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.PluginManager.PluginBase import PluginBase
import json
import shutil
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gtk
from loguru import logger

import globals as gl

from .actions.legacy_action import migrate_action_ids, migrate_action_settings
from .actions.play_sound.play_sound import PlaySoundAction
from .actions.stop_all.stop_all import StopAllAction

# Wiki
# https://streamcontroller.github.io/docs/latest/

# v1 typo'd Core447's own prefix (dev_core477 vs dev_core447); kept only so pages can be migrated off it
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
        self.migrate_legacy_pages()
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
        self.action_stop_all = ActionHolder(
            plugin_base=self,
            action_core=StopAllAction,
            action_id_suffix="StopAll",
            action_name=self.lm.get("action.stop-all.name"),
            action_support=action_support,
            description=self.lm.get("action.stop-all.description"),
            icon=logo_image(),
        )

        # Grouped because the chooser iterates loose holders as a set, so only a group keeps this order
        self.action_group = ActionHolderGroup(
            group_name=self.lm.get("plugin.group.name"),
            action_holders=[self.action_play_sound, self.action_stop_all],
        )
        # Both must be added individually: the action index is built from action_holders, not the group
        self.add_action_holder(self.action_play_sound)
        self.add_action_holder(self.action_stop_all)
        self.add_action_holder_group(self.action_group)

    def get_selector_icon(self) -> Gtk.Widget:
        return logo_image()

    def play_sound_action_id(self) -> str:
        return f"{self.get_plugin_id()}::PlaySound"

    def migrate_legacy_pages(self) -> tuple[int, int]:
        """Brings saved pages up to date. An old page imported later is rewritten on the next launch."""
        try:
            page_paths = gl.page_manager.get_pages()
        except Exception:
            return 0, 0

        ids = sounds = 0
        for page_path in page_paths:
            try:
                page_ids, page_sounds = self.migrate_page(Path(page_path))
            except Exception:  # one unwritable page must not stop the rest
                continue

            ids += page_ids
            sounds += page_sounds

        if ids or sounds:
            logger.info(f"EasySound migrated {ids} action ids and {sounds} sound lists")

        return ids, sounds

    def migrate_page(self, page_path: Path) -> tuple[int, int]:
        try:
            data = json.loads(page_path.read_text())
        except (OSError, ValueError):
            return 0, 0

        play_sound_id = self.play_sound_action_id()
        ids = migrate_action_ids(data, LEGACY_PLAY_SOUND_ACTION_ID, play_sound_id)

        # Runs for both ids: a page migrated by an earlier v2 build still holds single-filepath settings
        sounds = migrate_action_settings(
            data, {LEGACY_PLAY_SOUND_ACTION_ID, play_sound_id}
        )

        if not ids and not sounds:
            return 0, 0

        # The original goes outside the pages directory, where it cannot be picked up as a page itself
        backup_dir = Path(gl.DATA_PATH) / "easysound-v1-page-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / page_path.name
        if not backup.exists():
            shutil.copy2(page_path, backup)

        page_path.write_text(json.dumps(data, indent=4) + "\n")
        return ids, sounds

    def audio_server(self) -> dict:
        """Read fresh rather than cached, so a server started after StreamController is still found."""
        backend = getattr(self, "backend", None)
        if backend is None:
            return {"available": False, "name": "", "error": "backend unavailable"}

        try:
            info = backend.audio_server()

            return {
                "available": bool(info["available"]),
                "name": str(info["name"]),
                "error": str(info["error"]),
            }
        except Exception as error:  # rpyc reraises backend faults as arbitrary types
            return {"available": False, "name": "", "error": str(error)}

    def log_audio_server(self) -> None:
        info = self.audio_server()

        if info["available"]:
            logger.info(f"EasySound: audio server ready ({info['name'] or 'unknown'})")
            return

        # Told apart deliberately: a half-finished install looks nothing like a missing sound server
        if getattr(self, "backend", None) is None:
            logger.warning(
                "EasySound backend is not running. If the plugin was just installed or updated, "
                "__install__.py may still be building .venv, or pip may have failed; restarting "
                "StreamController once it finishes usually fixes this."
            )
            return

        # The only hard requirement: every output feature is built on PulseAudio's sink model
        logger.warning(
            "EasySound needs PulseAudio or PipeWire, and no sound server answered "
            f"({info['error']}). Sounds will not play until one is running."
        )

    def setup_backend(self):
        # Launch backend
        backend_path = Path(__file__).parent / "actions" / "backend.py"
        venv_path = Path(__file__).parent / ".venv"

        self.launch_backend(
            backend_path=backend_path, open_in_terminal=False, venv_path=venv_path
        )
        self.wait_for_backend()
        self.log_audio_server()
