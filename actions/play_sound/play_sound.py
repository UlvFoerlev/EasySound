from gi.repository import Adw, GLib, Gtk
from GtkHelper.ComboRow import SimpleComboRowItem
from GtkHelper.FileDialogRow import FileDialogFilter
from GtkHelper.GenerativeUI.ComboRow import ComboRow
from GtkHelper.GenerativeUI.EntryRow import EntryRow
from GtkHelper.GenerativeUI.ExpanderRow import ExpanderRow
from GtkHelper.GenerativeUI.ScaleRow import ScaleRow
from GtkHelper.GenerativeUI.SpinRow import SpinRow
from GtkHelper.GenerativeUI.SwitchRow import SwitchRow
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.EventAssigner import EventAssigner

from ..audio_targets import (
    ALL,
    CUSTOM,
    DEFAULT,
    GROUP_PREFIX,
    ICON_UNAVAILABLE,
    format_group_target,
    format_sink_target,
    missing_sinks,
    normalize_groups,
    resolve_target,
    sink_icon,
    target_icon,
    target_value,
)
from ..compat import FileDialogRow
from ..group_dialog import SpeakerGroupDialog
from ..icon_combo import IconComboRowItem, icon_factory
from ..modes import MODE_LOCALES, Mode
from ..sound_action_base import SoundActionBase
from ..spatial import (
    DEFAULT_ROOM_SIZE,
    channel_gains,
    clamp_position,
    clamp_room_size,
    merge_positions,
    normalize_positions,
    source_delays,
    stereo_balance,
)
from ..spatial_dialog import SpatialDialog

# Glob patterns, not MIME types: FileDialogFilter takes patterns, and they are case sensitive
AUDIO_SUFFIXES = ["mp3", "wav", "ogg", "oga", "opus", "flac", "m4a", "aiff", "aif", "au", "wma"]
AUDIO_FILE_PATTERNS = [f"*.{suffix}" for suffix in AUDIO_SUFFIXES] + [
    f"*.{suffix.upper()}" for suffix in AUDIO_SUFFIXES
]


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
    def spatial_enabled(self) -> bool:
        return self._get_property(key="spatial_enabled", default=False, enforce_type=bool)

    @property
    def spatial_source(self) -> tuple[float, float]:
        return clamp_position(self._get_property(key="spatial_source", default=[0.0, 0.0]))

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
                ),
                FileDialogFilter(
                    name=self.plugin_base.lm.get("action.play-sound.all_files"),
                    filters=["*"],
                ),
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

        # Sections are expanders; children use auto_add=False so the framework leaves them nested
        self.fades_section = ExpanderRow(
            action_core=self,
            var_name="section_fades",
            default_value=True,
            title="action.play-sound.section.fades",
            start_expanded=False,
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
            auto_add=False,
        )
        self.fades_section.add_row(self.fade_in_row.widget)

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
            auto_add=False,
        )
        self.fades_section.add_row(self.fade_out_row.widget)

        # Created last so it lands at the bottom: top-level order is creation order
        self.advanced_section = ExpanderRow(
            action_core=self,
            var_name="section_advanced",
            default_value=True,
            title="action.play-sound.section.advanced",
            start_expanded=False,
        )

        self.speakers_row = ComboRow(
            action_core=self,
            var_name="speakers",
            default_value=DEFAULT,
            items=self.speaker_items(),
            title="action.play-sound.speakers",
            subtitle=self.speakers_subtitle(),
            on_change=self.on_speakers_change,
            auto_add=False,
        )
        self.speakers_row.widget.set_factory(icon_factory())
        self.advanced_section.add_row(self.speakers_row.widget)

        self.spatial_row = SwitchRow(
            action_core=self,
            var_name="spatial_enabled",
            default_value=False,
            title="action.play-sound.spatial",
            subtitle="action.play-sound.spatial.subtitle",
            auto_add=False,
        )
        self.advanced_section.add_row(self.spatial_row.widget)

        # A plain row, not a generative one: it stores nothing and only opens the map
        self.spatial_button_row = Adw.ActionRow(
            title=self.plugin_base.lm.get("action.play-sound.spatial.position")
        )
        spatial_button = Gtk.Button(
            label=self.plugin_base.lm.get("action.play-sound.spatial.configure"),
            valign=Gtk.Align.CENTER,
        )
        spatial_button.connect("clicked", self.on_spatial_clicked)
        self.spatial_button_row.add_suffix(spatial_button)
        self.advanced_section.add_row(self.spatial_button_row)

        # The framework adds every auto_add row itself, so returning them here would double-parent them
        return []

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
                    "kind": str(sink["kind"]),
                    "bluetooth": bool(sink["bluetooth"]),
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

        self.refresh_speaker_items()

    def refresh_speaker_items(self) -> None:
        row = getattr(self, "speakers_row", None)
        if row is None:
            return

        # trigger_callback=False: repopulating is not a user selection and must not reopen the editor
        row.populate(
            self.speaker_items(),
            selected_item=self.speakers,
            update_settings=False,
            trigger_callback=False,
        )
        row.widget.set_subtitle(self.speakers_subtitle() or "")

    def speaker_positions(self) -> dict:
        return normalize_positions(self.plugin_base.get_settings().get("speaker_positions"))

    def save_speaker_positions(self, positions: dict) -> None:
        # Where a speaker physically stands belongs to the plugin, not to one action
        settings = self.plugin_base.get_settings()

        # Merged, never replaced: the dialog only ever knows this action's targets, not every speaker
        merged = merge_positions(settings.get("speaker_positions"), positions)
        settings["speaker_positions"] = {
            emitter: list(point) for emitter, point in merged.items()
        }
        self.plugin_base.set_settings(settings)

    def save_spatial_source(self, source) -> None:
        self._set_property(key="spatial_source", value=list(clamp_position(source)))

    def room_settings(self) -> tuple[float, bool]:
        # The room and its delay switch describe the physical setup, so they live with the plugin
        settings = self.plugin_base.get_settings()

        return (
            clamp_room_size(settings.get("room_size", DEFAULT_ROOM_SIZE)),
            bool(settings.get("spatial_delay", False)),
        )

    def save_room_settings(self, room_size: float, delay_enabled: bool) -> None:
        settings = self.plugin_base.get_settings()
        settings["room_size"] = clamp_room_size(room_size)
        settings["spatial_delay"] = bool(delay_enabled)
        self.plugin_base.set_settings(settings)

    def spatial_delays(self, sinks: list[str] | None) -> list[float] | None:
        if not self.spatial_enabled or not sinks:
            return None

        room_size, delay_enabled = self.room_settings()
        headsets = self.headset_sinks()
        speakers = [sink for sink in sinks if sink not in headsets]

        # Delays need two speakers to mean anything, and a worn device has no flight time at all
        if not delay_enabled or len(speakers) < 2:
            return None

        positions = self.speaker_positions()
        delays = source_delays(
            self.spatial_source,
            {sink: positions.get(sink, (0.0, 0.0)) for sink in speakers},
            room_size,
        )
        return [delays.get(sink, 0.0) for sink in sinks]

    def headset_sinks(self) -> set[str]:
        return {sink["name"] for sink in self.list_sinks() if sink.get("kind") == "headset"}

    def spatial_gains(self, sinks: list[str] | None) -> list[list[float]] | None:
        if not self.spatial_enabled:
            return None

        source = self.spatial_source

        # The default output has no known position, so only left/right balance can apply to it
        if sinks is None:
            return [list(stereo_balance(source[0]))]

        per_sink = channel_gains(
            source, sinks, self.speaker_positions(), self.headset_sinks()
        )
        return [list(per_sink.get(sink, (1.0, 1.0))) for sink in sinks]

    def on_spatial_clicked(self, _button):
        available = self.list_sinks()
        labels = {sink["name"]: sink["label"] for sink in available}
        room_size, delay_enabled = self.room_settings()

        # "Default" resolves to whichever sink the server currently prefers, so the map is never empty
        sinks = self.resolve_sinks()
        if sinks is None:
            default = next((sink["name"] for sink in available if sink["is_default"]), None)
            sinks = [default] if default else []

        # Held so the dialog outlives this call
        self.spatial_dialog = SpatialDialog(
            plugin=self.plugin_base,
            sinks=sinks,
            labels=labels,
            positions=self.speaker_positions(),
            source=self.spatial_source,
            on_positions_changed=self.save_speaker_positions,
            on_source_changed=self.save_spatial_source,
            room_size=room_size,
            delay_enabled=delay_enabled,
            on_room_changed=self.save_room_settings,
            headsets=self.headset_sinks(),
        )
        self.spatial_dialog.present(self.spatial_button_row)

    def resolve_sinks(self) -> list[str] | None:
        target = self.speakers

        if target in (DEFAULT, CUSTOM, ""):
            return None

        available = [sink["name"] for sink in self.list_sinks()]
        return resolve_target(target, available, self.speaker_groups())

    def speaker_items(self) -> list[IconComboRowItem]:
        lm = self.plugin_base.lm
        items = [
            IconComboRowItem(
                value=DEFAULT,
                label=lm.get("action.play-sound.speakers.default"),
                icon_name=target_icon(DEFAULT),
            ),
            IconComboRowItem(
                value=ALL,
                label=lm.get("action.play-sound.speakers.all"),
                icon_name=target_icon(ALL),
            ),
        ]

        items += [
            IconComboRowItem(
                value=format_sink_target(sink["name"]),
                label=sink["label"],
                icon_name=sink_icon(sink.get("kind", "speaker"), sink.get("bluetooth", False)),
            )
            for sink in self.list_sinks()
        ]
        items += [
            IconComboRowItem(
                value=format_group_target(group["id"]),
                label=group["name"],
                icon_name=target_icon(format_group_target(group["id"])),
            )
            for group in self.speaker_groups()
        ]

        # A saved selection whose device or group is gone still needs a row, or the combo shows another one
        target = self.speakers
        if target and target not in {item.get_value() for item in items}:
            items.append(
                IconComboRowItem(
                    value=target,
                    label=self.unavailable_label(target),
                    icon_name=ICON_UNAVAILABLE,
                )
            )

        items.append(
            IconComboRowItem(
                value=CUSTOM,
                label=lm.get("action.play-sound.speakers.custom"),
                icon_name=target_icon(CUSTOM),
            )
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
        # ComboRow passes item objects here, not the stored strings
        if target_value(new_value) != CUSTOM:
            return

        # "Custom..." acts as a button, so the previous selection is restored before opening the editor
        previous = target_value(old_value)
        previous = previous if previous and previous != CUSTOM else DEFAULT
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
                sinks = self.resolve_sinks()
                handle = backend.play(
                    path=self.filepath,
                    sinks=sinks,
                    volume=self.volume,
                    gains=self.spatial_gains(sinks),
                    delays=self.spatial_delays(sinks),
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
