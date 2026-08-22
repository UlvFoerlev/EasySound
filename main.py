# Import StreamController modules
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport
from src.backend.PluginManager.PluginBase import PluginBase
from pathlib import Path

import globals as gl

from .actions.play_sound.play_sound import PlaySoundAction

# Wiki
# https://streamcontroller.github.io/docs/latest/

# v1 typo'd Core447's own prefix (dev_core477 vs dev_core447); kept registered for backwards compatibility
LEGACY_PLAY_SOUND_ACTION_ID = "dev_core477_EasySound::PlaySound"


class PluginEasySound(PluginBase):
    def __init__(self):
        super().__init__()

        self.lm = self.locale_manager

        self.setup_backend()
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
        )
        self.add_action_holder(self.action_play_sound)

        # Registered only when in use: every registered holder gets a row in the action chooser, unconditionally
        if not self.legacy_action_in_use():
            return

        # Action ids resolve by exact match with no upstream alias support, so the old id is re-registered as-is
        self.action_play_sound_legacy = ActionHolder(
            plugin_base=self,
            action_core=PlaySoundAction,
            action_id=LEGACY_PLAY_SOUND_ACTION_ID,
            action_name=self.lm.get("action.play-sound.name-legacy"),
            action_support=action_support,
            description=self.lm.get("action.play-sound.description-legacy"),
        )
        self.add_action_holder(self.action_play_sound_legacy)

    def legacy_action_in_use(self) -> bool:
        # Fails open on any error: a hidden holder breaks pages, a needlessly shown one is only cosmetic
        try:
            page_paths = gl.page_manager.get_pages()
        except Exception:
            return True

        for page_path in page_paths:
            try:
                if LEGACY_PLAY_SOUND_ACTION_ID in Path(page_path).read_text():
                    return True
            except OSError:
                return True

        return False

    def setup_backend(self):
        # Launch backend
        backend_path = Path(__file__).parent / "actions" / "backend.py"
        venv_path = Path(__file__).parent / ".venv"

        self.launch_backend(
            backend_path=backend_path, open_in_terminal=False, venv_path=venv_path
        )
        self.wait_for_backend()
