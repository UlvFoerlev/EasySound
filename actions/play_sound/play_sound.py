from pathlib import Path

from gi.repository import Adw, Gtk, Pango
from GtkHelper.GtkHelper import ComboRow, ScaleRow

from ..chooser import ChooseFileDialog
from ..backend import InvalidSoundFileError
from ..modes import Mode
from ..sound_action_base import SoundActionBase


class PlaySoundAction(SoundActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.looping_channel = None
        self.active = False

    @property
    def filepath(self) -> str:
        val = self._get_property(key="filepath", default="", enforce_type=str)
        return val

    @filepath.setter
    def filepath(self, value: str):
        if not isinstance(value, str):
            return

        try:
            self.plugin_base.backend.preload_sound(value)
        except InvalidSoundFileError:
            self._set_property(key="filepath", value="")
            return

        self._set_property(key="filepath", value=value)

    @property
    def volume(self) -> float:
        return self._get_property(key="volume", default=100, enforce_type=float)

    @volume.setter
    def volume(self, value: float):
        self._set_property(key="volume", value=value)

    @property
    def fade_in(self) -> float:
        return self._get_property(key="fade_in", default=0.0, enforce_type=float)

    @fade_in.setter
    def fade_in(self, value: float):
        self._set_property(key="fade_in", value=value)

    @property
    def fade_out(self) -> float:
        return self._get_property(key="fade_out", default=0.0, enforce_type=float)

    @fade_out.setter
    def fade_out(self, value: float):
        self._set_property(key="fade_out", value=value)

    @property
    def mode(self) -> Mode:
        try:
            return Mode(
                self._get_property(
                    key="mode", default=Mode.PRESS.value, enforce_type=str
                )
            )
        except ValueError:
            return Mode.PRESS

    @mode.setter
    def mode(self, value: Mode):
        self._set_property(key="mode", value=str(value.value))

    @property
    def mode_index(self) -> int:
        return [x for x in Mode].index(self.mode)

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
            self.dropdown_option.append([mode.value])
            self.dropdown_name.append([mode.value])

        self.mode_cell_renderer = Gtk.CellRendererText(
            ellipsize=Pango.EllipsizeMode.END, max_width_chars=60
        )
        self.mode_row.combo_box.pack_start(self.mode_cell_renderer, True)
        self.mode_row.combo_box.add_attribute(
            self.mode_cell_renderer, "text", 0)

        self.mode_row.combo_box.set_active(self.mode_index)

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

    def setup_fade_box(self, base):
        # FADE IN
        self.fade_in_row = Adw.SpinRow().new_with_range(min=0, max=10, step=0.05)
        self.fade_in_row.set_title(
            self.plugin_base.lm.get("action.play-sound.fade-in.title")
        )
        self.fade_in_row.set_subtitle(
            self.plugin_base.lm.get("action.play-sound.fade-in.subtitle")
        )

        self.fade_in_row.set_value(self.fade_in)

        # FADE OUT
        self.fade_out_row = Adw.SpinRow().new_with_range(min=0, max=10, step=0.05)
        self.fade_out_row.set_title(
            self.plugin_base.lm.get("action.play-sound.fade-out.title")
        )
        self.fade_out_row.set_subtitle(
            self.plugin_base.lm.get("action.play-sound.fade-out.subtitle")
        )

        self.fade_out_row.set_value(self.fade_out)

        # Attach Methods
        self.fade_out_row.connect("changed", self.on_fade_change)
        self.fade_in_row.connect("changed", self.on_fade_change)
        self.setup_volumebox(base=base)
        self.setup_modebox(base=base)
        self.setup_fade_box(base=base)

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

        self.stop_looping()

    def on_volume_scale_change(self, entry):
        self.volume = entry.get_value()

    def on_select_mode(self, option):
        mode_index = option.get_active()
        mode = list(Mode)[mode_index]

        self.stop_looping()

        self.mode = mode

    def on_key_down(self):
        if not self.filepath:
            return

        self.active = not self.active

        match self.mode:
            case Mode.PRESS:
                self.plugin_base.backend.play_sound(
                    path=self.filepath,
                    volume=self.volume,
                    fade_in=self.fade_in,
                    immediate_fade_out=self.fade_out,
                )
            case Mode.TURN_ON:
                if self.active:
                    self.plugin_base.backend.play_sound(
                        path=self.filepath,
                        volume=self.volume,
                        fade_in=self.fade_in,
                        immediate_fade_out=self.fade_out,
                    )
            case Mode.TURN_OFF:
                if not self.active:
                    self.plugin_base.backend.play_sound(
                        path=self.filepath,
                        volume=self.volume,
                        fade_in=self.fade_in,
                        immediate_fade_out=self.fade_out,
                    )
            case Mode.HOLD:
                self.stop_looping()

                _, channel = self.plugin_base.backend.play_sound(
                    path=self.filepath,
                    volume=self.volume,
                    loops=-1,
                    fade_in=self.fade_in,
                )

                self.looping_channel = channel
            case Mode.PLAY_TILL_TURNED_OFF:
                if self.active:
                    _, channel = self.plugin_base.backend.play_sound(
                        path=self.filepath,
                        volume=self.volume,
                        loops=-1,
                        fade_in=self.fade_in,
                    )

                    self.looping_channel = channel
                elif not self.active:
                    self.stop_looping(fadeout=self.fade_out)

    def on_key_up(self):
        if self.filepath and Mode.RELEASE == self.mode:
            self.plugin_base.backend.play_sound(
                path=self.filepath, volume=self.volume)

    def on_fade_change(self, *args):
        self.fade_in = round(self.fade_in_row.get_value(), 2)
        self.fade_out = round(self.fade_out_row.get_value(), 2)

    def stop_looping(self, fadeout: float = 0.0):
        if self.looping_channel is None:
            return

        if not self.fade_out:
            self.looping_channel.stop()
        else:
            self.looping_channel.fadeout(int(fadeout * 1000))

        self.looping_channel = None
