from pathlib import Path

from gi.repository import Adw, GLib, Gtk, Pango
from GtkHelper.GtkHelper import ComboRow, ScaleRow
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.EventAssigner import EventAssigner

from ..chooser import ChooseFileDialog
from ..modes import Mode, MODE_LOCALES
from ..sound_action_base import SoundActionBase


class PlaySoundAction(SoundActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.looping_channel = None
        self.active = False
        self.validate_timeout = None

        # Dial DOWN/UP are kept so dial presses behave as they did under ActionBase's legacy dispatch
        self.add_event_assigner(
            EventAssigner(
                id="play_sound_pressed",
                ui_label=self.plugin_base.lm.get("action.play-sound.event.pressed"),
                default_events=[Input.Key.Events.DOWN, Input.Dial.Events.DOWN],
                callback=self.on_pressed,
            )
        )
        self.add_event_assigner(
            EventAssigner(
                id="play_sound_released",
                ui_label=self.plugin_base.lm.get("action.play-sound.event.released"),
                default_events=[Input.Key.Events.UP, Input.Dial.Events.UP],
                callback=self.on_released,
            )
        )

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

    def _sound_loads(self, path: str) -> bool:
        backend = getattr(self.plugin_base, "backend", None)
        if not path or backend is None:
            return False

        try:
            return bool(backend.preload_sound(path))
        except Exception:  # rpyc reraises backend and connection faults as arbitrary types
            return False

    def _play(self, **kwargs):
        backend = getattr(self.plugin_base, "backend", None)
        channel = None

        if backend is not None:
            try:
                _, channel = backend.play_sound(
                    path=self.filepath, volume=self.volume, **kwargs
                )
            except Exception:
                channel = None

        if channel is None:
            self.show_error(duration=2)

        return channel

    def _queue_filepath_validation(self):
        if self.validate_timeout is not None:
            GLib.source_remove(self.validate_timeout)

        self.validate_timeout = GLib.timeout_add(500, self._validate_filepath)

    def _validate_filepath(self):
        self.validate_timeout = None

        if not self.filepath or self._sound_loads(self.filepath):
            self.filepath_input.remove_css_class("error")
        else:
            self.filepath_input.add_css_class("error")

        return GLib.SOURCE_REMOVE

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

        self._queue_filepath_validation()

    def setup_modebox(self, base):
        self.dropdown_option = Gtk.ListStore.new([str])
        self.dropdown_name = Gtk.ListStore.new([str])
        self.mode_row = ComboRow(
            title=self.plugin_base.lm.get("action.play-sound.select_mode"),
            model=self.dropdown_name,
        )

        self.dropdown_option.clear()
        for mode in Mode:
            locale_key = MODE_LOCALES[mode]
            translation = self.plugin_base.lm.get(locale_key)
            self.dropdown_option.append([mode.value])
            self.dropdown_name.append([translation])

        self.mode_cell_renderer = Gtk.CellRendererText(
            ellipsize=Pango.EllipsizeMode.END, max_width_chars=60
        )
        self.mode_row.combo_box.pack_start(self.mode_cell_renderer, True)
        self.mode_row.combo_box.add_attribute(self.mode_cell_renderer, "text", 0)

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

        # ADD to UI
        base.append(self.fade_in_row)
        base.append(self.fade_out_row)

    def get_config_rows(self):
        base = super().get_config_rows()
        self.setup_filebox(base=base)
        self.setup_volumebox(base=base)
        self.setup_modebox(base=base)
        self.setup_fade_box(base=base)

        return base

    def _set_filepath(self, result: Path):
        self.filepath = str(result)
        self.filepath_input.set_text(self.filepath)

    def on_filepath_browse_click(self, entry):
        # Held so the dialog outlives this call; open() returns before the user picks
        self.file_dialog = ChooseFileDialog(
            plugin=self.plugin_base,
            dialog_name="Select Audio File",
            setter_func=self._set_filepath,
        )

    def on_filepath_change(self, entry, _):
        self.filepath = entry.get_text()

        self.stop_looping()
        self._queue_filepath_validation()

    def on_volume_scale_change(self, entry):
        self.volume = entry.get_value()

    def on_select_mode(self, option):
        mode_index = option.get_active()
        mode = list(Mode)[mode_index]

        self.stop_looping()
        self.active = False

        self.mode = mode

    def on_pressed(self, data) -> None:
        if not self.filepath:
            return

        match self.mode:
            case Mode.PRESS:
                self._play(fade_in=self.fade_in, fade_out=self.fade_out)
            case Mode.TURN_ON:
                self.active = not self.active
                if self.active:
                    self._play(fade_in=self.fade_in, fade_out=self.fade_out)
            case Mode.TURN_OFF:
                self.active = not self.active
                if not self.active:
                    self._play(fade_in=self.fade_in, fade_out=self.fade_out)
            case Mode.HOLD:
                self.stop_looping()

                self.looping_channel = self._play(loops=-1, fade_in=self.fade_in)

            case Mode.PLAY_TILL_TURNED_OFF:
                self.active = not self.active
                if self.active:
                    self.looping_channel = self._play(loops=-1, fade_in=self.fade_in)

                else:
                    self.stop_looping(fadeout=self.fade_out)

    def on_released(self, data) -> None:
        if self.filepath and Mode.RELEASE == self.mode:
            self._play(fade_in=self.fade_in, fade_out=self.fade_out)

        elif self.filepath and self.mode == Mode.HOLD:
            self.stop_looping(fadeout=self.fade_out)

    def on_fade_change(self, *args):
        self.fade_in = round(self.fade_in_row.get_value(), 2)
        self.fade_out = round(self.fade_out_row.get_value(), 2)

    def stop_looping(self, fadeout: float = 0.0):
        if self.looping_channel is None:
            return

        if not fadeout:
            self.looping_channel.stop()
        else:
            self.looping_channel.fadeout(int(fadeout * 1000))

        self.looping_channel = None
