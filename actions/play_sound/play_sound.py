from ..sound_action_base import SoundActionBase
from gi.repository import Adw, Gtk
from GtkHelper.GtkHelper import ScaleRow
from ..chooser import ChooseFileDialog


class PlaySoundAction(SoundActionBase):
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
        self.filepath_browse = Gtk.Button.new_with_label(
            self.plugin_base.lm.get("action.play-sound.browse")
        )

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
        self.filepath_browse.connect("clicked", self.on_filepath_browse_click)
        self.filepath_input.connect("notify::text", self.on_filepath_change)
        self.volume_scale.adjustment.connect(
            "value-changed", self.on_volume_scale_change
        )

        base = super().get_config_rows()

        base.append(self.filepath_browse)
        base.append(self.filepath_input)
        base.append(self.volume_scale)

        return base

    def on_filepath_browse_click(self, entry):
        file_dialog = ChooseFileDialog(dialog_name="Select Audio File")

        self.filepath = file_dialog.selected_file or ""

    def on_filepath_change(self, entry, _):
        self.filepath = entry.get_text()

    def on_volume_scale_change(self, entry):
        self.volume = entry.get_value()

    def on_key_down(self):
        print(self.backend, self.filepath)
        if self.filepath:
            self.backend.play_sound()
