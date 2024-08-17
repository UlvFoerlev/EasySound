from pathlib import Path

from gi.repository import Adw, Gtk, Pango
from GtkHelper.GtkHelper import ComboRow, ScaleRow

from ..chooser import ChooseFileDialog
from ..modes import Mode
from ..sound_action_base import SoundActionBase


class PlaySoundAction(SoundActionBase):
    @property
    def filepath(self) -> str:
        val = self._get_property(key="filepath", default="", enforce_type=str)
        return val

    @filepath.setter
    def filepath(self, value: str):
        if not isinstance(value, str):
            return

        self._set_property(key="filepath", value=value)

    @property
    def volume(self) -> float:
        return self._get_property(key="volume", default=100, enforce_type=float)

    @volume.setter
    def volume(self, value: float):
        self._set_property(key="volume", value=value)

    @property
    def mode(self) -> Mode:
        return Mode(
            self._get_property(key="mode", default=Mode.PRESS, enforce_type=Mode)
        )

    @mode.setter
    def mode(self, value: Mode):
        self._set_property(key="mode", value=str(value))

    def setup_filebox(self, base):
        self.filebox_name = Gtk.ListStore.new([str])
        self.filebox = ComboRow(
            title=self.plugin_base.lm.get("action.play-sound.sound_file"),
            model=self.filebox_name,
        )

        self.filepath_browse = Gtk.Button.new_with_label(
            self.plugin_base.lm.get("action.play-sound.browse")
        )

        self.filepath_input = Adw.EntryRow(
            title=self.plugin_base.lm.get("action.play-sound.filepath")
        )

        self.filepath_input.set_text(self.filepath)

        self.filepath_browse.connect("clicked", self.on_filepath_browse_click)
        self.filepath_input.connect("notify::text", self.on_filepath_change)

        self.filebox.main_box.append(self.filepath_input)
        self.filebox.main_box.append(self.filepath_browse)

        base.append(self.filebox)

    def setup_modebox(self, base):
        self.dropdown_option = Gtk.ListStore.new([str])
        self.dropdown_name = Gtk.ListStore.new([str])
        self.mode_row = ComboRow(
            title=self.plugin_base.lm.get("action.play-sound.select_mode"),
            model=self.dropdown_name,
        )

        self.dropdown_option.clear()
        for mode in Mode:
            self.dropdown_option.append([mode, mode.value])
            self.dropdown_name.append([mode, mode.value])

        self.mode_cell_renderer = Gtk.CellRendererText(
            ellipsize=Pango.EllipsizeMode.END, max_width_chars=60
        )
        self.mode_row.combo_box.pack_start(self.mode_cell_renderer, True)
        self.mode_row.combo_box.add_attribute(self.mode_cell_renderer, "text", 0)

        self.mode_row.combo_box.set_entry_text_column(Mode.PRESS)

        # Connect entries
        self.mode_row.combo_box.connect("changed", self.on_select_mode)

        base.append(self.mode_row)

    def setup_volumebox(self, base):
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

        self.volume_scale.adjustment.connect(
            "value-changed", self.on_volume_scale_change
        )

        base.append(self.volume_scale)

    def get_config_rows(self):
        base = super().get_config_rows()
        self.setup_filebox(base=base)
        self.setup_volumebox(base=base)
        self.setup_modebox(base=base)

        return base

    def _set_filepath(self, result: Path):
        self.filepath = str(result)
        self.filepath_input.set_text(self.filepath)

    def on_filepath_browse_click(self, entry):
        file_dialog = ChooseFileDialog(
            plugin=self.plugin_base,
            dialog_name="Select Audio File",
            setter_func=self._set_filepath,
        )

        self.filepath = file_dialog.selected_file or ""

    def on_filepath_change(self, entry, _):
        self.filepath = entry.get_text()

    def on_volume_scale_change(self, entry):
        self.volume = entry.get_value()

    def on_select_mode(self, mode: Mode):
        self.mode = mode

    def on_key_down(self):
        if self.filepath and Mode.PRESS == self.mode:
            self.plugin_base.backend.play_sound(path=self.filepath, volume=self.volume)

    def on_key_release(self):
        if self.filepath and Mode.RELEASE == self.mode:
            self.plugin_base.backend.play_sound(path=self.filepath, volume=self.volume)
