from gi.repository import GLib
from GtkHelper.ComboRow import SimpleComboRowItem
from GtkHelper.FileDialogRow import FileDialogFilter
from GtkHelper.GenerativeUI.ComboRow import ComboRow
from GtkHelper.GenerativeUI.EntryRow import EntryRow
from GtkHelper.GenerativeUI.ScaleRow import ScaleRow
from GtkHelper.GenerativeUI.SpinRow import SpinRow
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.EventAssigner import EventAssigner

from ..audio_targets import (
    ALL,
    CUSTOM,
    DEFAULT,
    GROUP_PREFIX,
    format_group_target,
    format_sink_target,
    missing_sinks,
    normalize_groups,
    resolve_target,
)
from ..compat import FileDialogRow
from ..group_dialog import SpeakerGroupDialog
from ..modes import MODE_LOCALES, Mode
from ..sound_action_base import SoundActionBase

# Glob patterns, not MIME types: FileDialogFilter takes patterns
AUDIO_FILE_PATTERNS = ["*.mp3", "*.wav", "*.ogg", "*.oga", "*.opus", "*.flac"]


class PlaySoundAction(SoundActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.looping_handle = None
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
    def speakers(self) -> str:
        return self._get_property(key="speakers", default=DEFAULT, enforce_type=str)

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

        self.speakers_row = ComboRow(
            action_core=self,
            var_name="speakers",
            default_value=DEFAULT,
            items=self.speaker_items(),
            title="action.play-sound.speakers",
            subtitle=self.speakers_subtitle(),
            on_change=self.on_speakers_change,
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

    def list_sinks(self) -> list[dict]:
        backend = getattr(self.plugin_base, "backend", None)
        if backend is None:
            return []

        try:
            # Copied out of the rpyc netrefs so the rest of the frontend works on plain values
            return [
                {
                    "name": str(sink["name"]),
                    "label": str(sink["label"]),
                    "is_default": bool(sink["is_default"]),
                }
                for sink in backend.list_sinks()
            ]
        except Exception:  # rpyc reraises backend and connection faults as arbitrary types
            return []

    def speaker_groups(self) -> list[dict]:
        return normalize_groups(self.plugin_base.get_settings().get("speaker_groups"))

    def save_speaker_groups(self, groups: list[dict]) -> None:
        # Plugin settings rather than action settings, so every action and page shares the groups
        settings = self.plugin_base.get_settings()
        settings["speaker_groups"] = groups
        self.plugin_base.set_settings(settings)

    def resolve_sinks(self) -> list[str] | None:
        target = self.speakers

        if target in (DEFAULT, CUSTOM, ""):
            return None

        available = [sink["name"] for sink in self.list_sinks()]
        return resolve_target(target, available, self.speaker_groups())

    def speaker_items(self) -> list[SimpleComboRowItem]:
        lm = self.plugin_base.lm
        items = [
            SimpleComboRowItem(
                value=DEFAULT, label=lm.get("action.play-sound.speakers.default")
            ),
            SimpleComboRowItem(value=ALL, label=lm.get("action.play-sound.speakers.all")),
        ]

        items += [
            SimpleComboRowItem(value=format_sink_target(sink["name"]), label=sink["label"])
            for sink in self.list_sinks()
        ]
        items += [
            SimpleComboRowItem(value=format_group_target(group["id"]), label=group["name"])
            for group in self.speaker_groups()
        ]

        # A saved selection whose device or group is gone still needs a row, or the combo shows another one
        target = self.speakers
        if target and target not in {item.get_value() for item in items}:
            items.append(
                SimpleComboRowItem(value=target, label=self.unavailable_label(target))
            )

        items.append(
            SimpleComboRowItem(value=CUSTOM, label=lm.get("action.play-sound.speakers.custom"))
        )
        return items

    def unavailable_label(self, target: str) -> str:
        lm = self.plugin_base.lm
        suffix = lm.get("action.play-sound.speakers.unavailable")

        if target.startswith(GROUP_PREFIX):
            return f"{lm.get('action.play-sound.groups.deleted')} {suffix}"

        return f"{target.split(':', 1)[-1]} {suffix}"

    def speakers_subtitle(self) -> str | None:
        available = [sink["name"] for sink in self.list_sinks()]
        absent = missing_sinks(self.speakers, available, self.speaker_groups())
        if not absent:
            return None

        return f"{self.plugin_base.lm.get('action.play-sound.speakers.missing')} {', '.join(absent)}"

    def on_speakers_change(self, widget, new_value, old_value):
        if new_value != CUSTOM:
            return

        # "Custom..." acts as a button, so the previous selection is restored before opening the editor
        previous = old_value if old_value and old_value != CUSTOM else DEFAULT
        self.speakers_row.set_value(previous)
        self.speakers_row.set_ui_value(previous)
        self.open_group_dialog()

    def open_group_dialog(self):
        # Held so the dialog outlives this call
        self.group_dialog = SpeakerGroupDialog(
            plugin=self.plugin_base,
            sinks=self.list_sinks(),
            groups=self.speaker_groups(),
            on_saved=self.save_speaker_groups,
        )
        self.group_dialog.present(self.speakers_row.widget)

    def _play(self, **kwargs):
        backend = getattr(self.plugin_base, "backend", None)
        handle = None

        if backend is not None:
            try:
                handle = backend.play(
                    path=self.filepath,
                    sinks=self.resolve_sinks(),
                    volume=self.volume,
                    **kwargs,
                )
            except Exception:
                handle = None

        if handle is None:
            self.show_error(duration=2)

        return handle

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

                self.looping_handle = self._play(loops=-1, fade_in=self.fade_in)

            case Mode.PLAY_TILL_TURNED_OFF:
                self.active = not self.active
                if self.active:
                    self.looping_handle = self._play(loops=-1, fade_in=self.fade_in)

                else:
                    self.stop_looping(fadeout=self.fade_out)

    def on_released(self, data) -> None:
        if self.filepath and Mode.RELEASE == self.mode:
            self._play(fade_in=self.fade_in, fade_out=self.fade_out)

        elif self.filepath and self.mode == Mode.HOLD:
            self.stop_looping(fadeout=self.fade_out)

    def stop_looping(self, fadeout: float = 0.0):
        if self.looping_handle is None:
            return

        backend = getattr(self.plugin_base, "backend", None)
        if backend is not None:
            try:
                backend.stop(self.looping_handle, fadeout)
            except Exception:
                pass

        self.looping_handle = None
