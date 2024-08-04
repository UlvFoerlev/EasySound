from ..sound_base import SoundBase
from gi.repository import Adw, Gtk
from GtkHelper.GtkHelper import ScaleRow


class PlaySoundAction(SoundBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def filepath(self) -> str:
        val = self._get_property(key="filepath", default="", enforce_type=str)
        return val

    @filepath.setter
    def filepath(self, value: str):
        self._set_property(key="filepath", value=value)

    @property
    def volume(self) -> float:
        return self._get_property(key="volume", default=100, enforce_type=float)

    @volume.setter
    def volume(self, value: float):
        self._set_property(key="volume", value=value)

    def get_config_rows(self):
        self.filepath_input = Adw.EntryRow(
            title=self.plugin_base.lm.get("action.play-sound.filepath")
        )

        self.filepath_input.set_text(self.filepath)

        self.volume_scale = ScaleRow(
            title=self.plugin_base.lm.get("action.generic.volume"),
            value=self.volume,
            min=0,
            max=100,
            step=1,
            text_left="0",
            text_right="100",
        )
        self.volume_scale.scale.set_draw_value(True)

        # Connect entries
        self.filepath_input.connect("notify::text", self.on_filepath_change)
        self.volume_scale.adjustment.connect(
            "value-changed", self.on_volume_scale_change
        )

        base = super().get_config_rows()

        base.append(self.filepath_input)
        base.append(self.volume_scale)

        return base

    def on_filepath_change(self, entry, _):
        self.filepath = entry.get_text()

    def on_volume_scale_change(self, entry):
        self.volume = entry.get_value()
