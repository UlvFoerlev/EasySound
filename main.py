# Import StreamController modules
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder
from pathlib import Path

from .actions.play_sound.play_sound import PlaySoundAction

# Wiki
# https://core447.com/streamcontroller/docs/latest/


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
            plugin_version="1.0.0",
            app_version="1.5.0-beta",
        )

    def setup_actions(self):
        self.action_play_sound = ActionHolder(
            plugin_base=self,
            action_base=PlaySoundAction,
            action_id="dev_core477_EasySound::PlaySound",
            action_name=self.lm.get("action.play-sound.name"),
        )
        self.add_action_holder(self.action_play_sound)

    def setup_backend(self):
        # Launch backend
        backend_path = Path(__file__).parent / "actions" / "backend.py"
        venv_path = Path(__file__).parent / ".venv"

        self.launch_backend(
            backend_path=backend_path, open_in_terminal=False, venv_path=venv_path
        )
        self.wait_for_backend(tries=5)
