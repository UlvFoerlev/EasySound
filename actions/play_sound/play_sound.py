from gi.repository import GLib
from GtkHelper.ComboRow import SimpleComboRowItem
from GtkHelper.FileDialogRow import FileDialogFilter
from GtkHelper.GenerativeUI.ComboRow import ComboRow
from GtkHelper.GenerativeUI.EntryRow import EntryRow
from GtkHelper.GenerativeUI.FileDialogRow import FileDialogRow
from GtkHelper.GenerativeUI.ScaleRow import ScaleRow
from GtkHelper.GenerativeUI.SpinRow import SpinRow
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.EventAssigner import EventAssigner

from ..modes import MODE_LOCALES, Mode
from ..sound_action_base import SoundActionBase

# Glob patterns, not MIME types: FileDialogFilter takes patterns
AUDIO_FILE_PATTERNS = ["*.mp3", "*.wav", "*.ogg", "*.oga", "*.opus", "*.flac"]


class PlaySoundAction(SoundActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.looping_channel = None
        self.active = False
        self.validate_timeout = None
        self.warmed_path = None

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

    def on_ready(self) -> None:
        self.warm_sound_cache()

    def warm_sound_cache(self) -> None:
        # on_update calls on_ready by default, so the guard keeps this to one warm-up per path
        path = self.filepath
        if not path or path == self.warmed_path:
            return

        backend = getattr(self.plugin_base, "backend", None)
        if backend is None:
            return

        try:
            backend.warm_sound(path)
        except Exception:  # rpyc reraises backend and connection faults as arbitrary types
            return

        self.warmed_path = path

    @property
    def filepath(self) -> str:
        return self._get_property(key="filepath", default="", enforce_type=str)

    @property
    def volume(self) -> float:
        return self._get_property(key="volume", default=100.0, enforce_type=float)

    @property
    def fade_in(self) -> float:
        return self._get_property(key="fade_in", default=0.0, enforce_type=float)

    @property
    def fade_out(self) -> float:
        return self._get_property(key="fade_out", default=0.0, enforce_type=float)

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

    def get_config_rows(self):
        # generative_ui_objects is never cleared upstream, so rebuild it to avoid duplicated rows
        self.generative_ui_objects.clear()

        self.filepath_row = FileDialogRow(
            action_core=self,
            var_name="filepath",
            default_value="",
            title="action.play-sound.sound_file",
            dialog_title="action.play-sound.select_file",
            only_show_filename=False,
            filters=[
                FileDialogFilter(
                    name=self.plugin_base.lm.get("action.play-sound.audio_files"),
                    filters=AUDIO_FILE_PATTERNS,
                )
            ],
            on_change=self.on_filepath_picked,
        )

        # Paired with the dialog row so a path can still be typed or pasted; both write "filepath"
        self.filepath_entry = EntryRow(
            action_core=self,
            var_name="filepath",
            default_value="",
            title="action.play-sound.filepath",
            on_change=self.on_filepath_typed,
        )

        self.volume_row = ScaleRow(
            action_core=self,
            var_name="volume",
            default_value=100.0,
            min=0,
            max=100,
            step=1,
            digits=0,
            title="action.generic.volume",
        )

        self.mode_row = ComboRow(
            action_core=self,
            var_name="mode",
            default_value=Mode.PRESS.value,
            items=[
                SimpleComboRowItem(
                    value=mode.value,
                    label=self.plugin_base.lm.get(MODE_LOCALES[mode]),
                )
                for mode in Mode
            ],
            title="action.play-sound.select_mode",
            on_change=self.on_mode_change,
        )

        self.fade_in_row = SpinRow(
            action_core=self,
            var_name="fade_in",
            default_value=0.0,
            min=0,
            max=10,
            step=0.05,
            digits=2,
            title="action.play-sound.fade-in.title",
            subtitle="action.play-sound.fade-in.subtitle",
        )

        self.fade_out_row = SpinRow(
            action_core=self,
            var_name="fade_out",
            default_value=0.0,
            min=0,
            max=10,
            step=0.05,
            digits=2,
            title="action.play-sound.fade-out.title",
            subtitle="action.play-sound.fade-out.subtitle",
        )

        return self.get_generative_ui_widgets()

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
        path = self.filepath

        if not path or self._sound_loads(path):
            self.filepath_entry.widget.remove_css_class("error")
            self.warmed_path = path or None  # _sound_loads already decoded it into the backend cache
            if path:
                # set_ui_value manages the widget's own signals, so syncing the sibling cannot loop
                self.filepath_row.set_ui_value(path)
        else:
            self.filepath_entry.widget.add_css_class("error")

        return GLib.SOURCE_REMOVE

    def on_filepath_picked(self, widget, new_value, old_value):
        self.stop_looping()
        self.filepath_entry.set_ui_value(new_value or "")
        self._queue_filepath_validation()

    def on_filepath_typed(self, widget, new_value, old_value):
        self.stop_looping()
        self._queue_filepath_validation()

    def on_mode_change(self, widget, new_value, old_value):
        self.stop_looping()
        self.active = False

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

    def stop_looping(self, fadeout: float = 0.0):
        if self.looping_channel is None:
            return

        if not fadeout:
            self.looping_channel.stop()
        else:
            self.looping_channel.fadeout(int(fadeout * 1000))

        self.looping_channel = None
