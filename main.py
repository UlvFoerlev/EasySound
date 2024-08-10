# Import StreamController modules
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder

# Import actions
from .actions.play_sound.play_sound import PlaySoundAction

# Wiki
# https://core447.com/streamcontroller/docs/latest/


class PluginEasySound(PluginBase):
    def __init__(self):
        super().__init__()

        self.lm = self.locale_manager

        self.action_play_sound = ActionHolder(
            plugin_base=self,
            action_base=PlaySoundAction,
            action_id="dev_core477_EasySound::PlaySound",
            action_name=self.lm.get("action.play-sound.name"),
        )
        self.add_action_holder(self.action_play_sound)

        # Register plugin
        self.register(
            plugin_name="EasySound",
            github_repo="https://github.com/StreamController/PluginTemplate",
            plugin_version="1.0.0",
            app_version="1.1.1-alpha",
        )
