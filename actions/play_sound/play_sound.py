from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk
from GtkHelper.ComboRow import SimpleComboRowItem
from GtkHelper.GenerativeUI.ComboRow import ComboRow
from GtkHelper.GenerativeUI.ExpanderRow import ExpanderRow
from GtkHelper.GenerativeUI.ScaleRow import ScaleRow
from GtkHelper.GenerativeUI.SpinRow import SpinRow
from GtkHelper.GenerativeUI.SwitchRow import SwitchRow
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.EventAssigner import EventAssigner
from src.Signals import Signals

from ..audio_targets import (
    GROUP_PREFIX,
    ICON_UNAVAILABLE,
    SinkKind,
    Target,
    format_group_target,
    format_sink_target,
    missing_sinks,
    normalize_groups,
    resolve_target,
    sink_icon,
    target_icon,
    target_value,
)
from ..group_dialog import SpeakerGroupDialog
from ..icon_combo import IconComboRowItem, icon_factory
from ..modes import MODE_LOCALES, Mode
from ..playlist import (
    ORDER_LOCALES,
    Order,
    Picker,
    normalize_order,
    rate_scale,
    resolve_sounds,
)
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

        self.active = False
        self.warmed_paths: set[str] = set()
        # Rotation and shuffle state is per action and deliberately not persisted
        self.picker = Picker()

        # A loop is stopped when its page is left, unless the action opts out of that
        self.connect(signal=Signals.ChangePage, callback=self.on_page_changed)
        # Deleting the page takes its sounds with it, whatever the keep-playing flag says
        self.connect(signal=Signals.PageDelete, callback=self.on_page_deleted)

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

    def sound_pool(self) -> list[str]:
        return resolve_sounds(
            self._get_property(key="sounds", default=None),
            self.filepath,
            self.extra_filepaths,
        )

    def warm_sound_cache(self) -> None:
        # on_update calls on_ready by default, so the guard keeps this to one warm-up per path
        pending = [path for path in self.sound_pool() if path not in self.warmed_paths]
        if not pending:
            return

        backend = getattr(self.plugin_base, "backend", None)
        if backend is None:
            return

        for path in pending:
            try:
                backend.warm_sound(path)
            except Exception:  # rpyc reraises backend and connection faults as arbitrary types
                return

            self.warmed_paths.add(path)

    @property
    def filepath(self) -> str:
        return self._get_property(key="filepath", default="", enforce_type=str)

    @property
    def extra_filepaths(self) -> list:
        return self._get_property(key="extra_filepaths", default=[], enforce_type=list)

    @property
    def playback_order(self) -> Order:
        return normalize_order(
            self._get_property(key="playback_order", default=Order.RANDOM.value)
        )

    @property
    def rate_variation(self) -> float:
        return self._get_property(key="rate_variation", default=0.0, enforce_type=float)

    @property
    def speakers(self) -> str:
        return self._get_property(key="speakers", default=Target.DEFAULT.value, enforce_type=str)

    @property
    def keep_playing_off_page(self) -> bool:
        return self._get_property(
            key="keep_playing_off_page", default=False, enforce_type=bool
        )

    @property
    def pause_instead_of_stop(self) -> bool:
        return self._get_property(
            key="pause_instead_of_stop", default=False, enforce_type=bool
        )

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

        self.sounds_section = ExpanderRow(
            action_core=self,
            var_name="section_sounds",
            default_value=True,
            title="action.play-sound.sounds",
            subtitle="action.play-sound.sounds.subtitle",
            start_expanded=True,
        )

        # Nested as the section's last child, and only meaningful once there are several sounds
        self.order_row = ComboRow(
            action_core=self,
            var_name="playback_order",
            default_value=Order.RANDOM.value,
            items=[
                SimpleComboRowItem(
                    value=order.value, label=self.plugin_base.lm.get(ORDER_LOCALES[order])
                )
                for order in Order
            ],
            title="action.play-sound.order",
            auto_add=False,
        )
        self.rebuild_sounds_section()

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

        self.keep_playing_row = SwitchRow(
            action_core=self,
            var_name="keep_playing_off_page",
            default_value=False,
            title="action.play-sound.keep-playing",
            subtitle="action.play-sound.keep-playing.subtitle",
        )

        self.pause_row = SwitchRow(
            action_core=self,
            var_name="pause_instead_of_stop",
            default_value=False,
            title="action.play-sound.pause-mode",
            subtitle="action.play-sound.pause-mode.subtitle",
        )
        self.update_loop_option_visibility()

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
            default_value=Target.DEFAULT.value,
            items=self.speaker_items(),
            title="action.play-sound.speakers",
            subtitle=self.speakers_subtitle(),
            on_change=self.on_speakers_change,
            auto_add=False,
        )
        self.speakers_row.widget.set_factory(icon_factory())
        self.advanced_section.add_row(self.speakers_row.widget)

        self.variation_row = SpinRow(
            action_core=self,
            var_name="rate_variation",
            default_value=0.0,
            min=0,
            max=50,
            step=1,
            digits=0,
            title="action.play-sound.variation",
            subtitle="action.play-sound.variation.subtitle",
            auto_add=False,
        )
        self.advanced_section.add_row(self.variation_row.widget)

        self.spatial_row = SwitchRow(
            action_core=self,
            var_name="spatial_enabled",
            default_value=False,
            title="action.play-sound.spatial",
            subtitle="action.play-sound.spatial.subtitle",
            on_change=self.on_spatial_toggled,
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
        # Nothing reads the map while spatial is off, so the row is not clickable until it is on
        self.spatial_button_row.set_sensitive(self.spatial_enabled)
        self.advanced_section.add_row(self.spatial_button_row)

        # The framework adds every auto_add row itself, so returning them here would double-parent them
        return []

    def rebuild_sounds_section(self) -> None:
        lm = self.plugin_base.lm
        pool = self.sound_pool()
        self.sounds_section.clear_rows()

        for path in pool:
            row = Adw.ActionRow(title=Path(path).name, subtitle=path)

            # Checked locally rather than through the backend: a missing file is the common mistake
            if not Path(path).is_file():
                missing = Gtk.Image(
                    icon_name="dialog-warning-symbolic",
                    valign=Gtk.Align.CENTER,
                    tooltip_text=lm.get("action.play-sound.sounds.missing"),
                )
                row.add_suffix(missing)

            remove = Gtk.Button(
                icon_name="user-trash-symbolic",
                valign=Gtk.Align.CENTER,
                css_classes=["flat"],
                tooltip_text=lm.get("action.play-sound.sounds.remove"),
            )
            remove.connect("clicked", self.on_remove_sound, path)
            row.add_suffix(remove)
            self.sounds_section.add_row(row)

        add_row = Adw.ActionRow(title=lm.get("action.play-sound.sounds.add"))
        add_button = Gtk.Button(
            label=lm.get("action.play-sound.sounds.browse"),
            valign=Gtk.Align.CENTER,
            css_classes=["suggested-action"] if not pool else [],
        )
        add_button.connect("clicked", self.on_add_sounds_clicked)
        add_row.add_suffix(add_button)
        self.sounds_section.add_row(add_row)

        self.update_order_visibility()

    def update_order_visibility(self) -> None:
        row = getattr(self, "order_row", None)
        if row is None:
            return

        # Re-added last on every rebuild, so it stays the final child of the section
        self.sounds_section.add_row(row.widget)
        # Nothing to order with a single sound, so it only appears once there are several
        row.widget.set_visible(len(self.sound_pool()) > 1)

    def save_sounds(self, paths: list) -> None:
        # Writing "sounds" retires the pre-list settings for this action without touching them
        self._set_property(key="sounds", value=list(paths))
        self.rebuild_sounds_section()
        self.warm_sound_cache()

    def on_remove_sound(self, _button, path: str) -> None:
        self.save_sounds([kept for kept in self.sound_pool() if kept != path])

    def on_add_sounds_clicked(self, _button) -> None:
        audio_filter = Gtk.FileFilter()
        audio_filter.set_name(self.plugin_base.lm.get("action.play-sound.audio_files"))
        for pattern in AUDIO_FILE_PATTERNS:
            audio_filter.add_pattern(pattern)

        # Patterns are case sensitive and the list is not exhaustive, so an escape hatch is offered
        all_filter = Gtk.FileFilter()
        all_filter.set_name(self.plugin_base.lm.get("action.play-sound.all_files"))
        all_filter.add_pattern("*")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(audio_filter)
        filters.append(all_filter)

        # Held so the dialog outlives this call, as open_multiple returns before the user picks
        self.sounds_dialog = Gtk.FileDialog(
            title=self.plugin_base.lm.get("action.play-sound.sounds.add"),
            filters=filters,
            default_filter=audio_filter,
        )
        self.sounds_dialog.open_multiple(callback=self.on_sounds_chosen)

    def on_sounds_chosen(self, dialog, result) -> None:
        try:
            chosen = dialog.open_multiple_finish(result)
        except GLib.Error:  # the user cancelled, which is not an error worth reporting
            return

        added = self.sound_pool()
        for index in range(chosen.get_n_items()):
            path = chosen.get_item(index).get_path()
            # A non-local location has no filesystem path, so it cannot be played
            if path and path not in added:
                added.append(path)

        self.save_sounds(added)

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

    def plugin_settings(self, settings: dict | None = None) -> dict:
        # Passed in on the key-press path, so one press reads the settings file at most once
        return settings if settings is not None else self.plugin_base.get_settings()

    def speaker_groups(self, settings: dict | None = None) -> list[dict]:
        return normalize_groups(self.plugin_settings(settings).get("speaker_groups"))

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

    def speaker_positions(self, settings: dict | None = None) -> dict:
        return normalize_positions(self.plugin_settings(settings).get("speaker_positions"))

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

    def room_settings(self, settings: dict | None = None) -> tuple[float, bool]:
        # The room and its delay switch describe the physical setup, so they live with the plugin
        settings = self.plugin_settings(settings)

        return (
            clamp_room_size(settings.get("room_size", DEFAULT_ROOM_SIZE)),
            bool(settings.get("spatial_delay", False)),
        )

    def save_room_settings(self, room_size: float, delay_enabled: bool) -> None:
        settings = self.plugin_base.get_settings()
        settings["room_size"] = clamp_room_size(room_size)
        settings["spatial_delay"] = bool(delay_enabled)
        self.plugin_base.set_settings(settings)

    def spatial_delays(
        self,
        sinks: list[str] | None,
        available: list[dict] | None = None,
        settings: dict | None = None,
    ) -> list[float] | None:
        if not self.spatial_enabled or not sinks:
            return None

        room_size, delay_enabled = self.room_settings(settings)
        headsets = self.headset_sinks(available)
        speakers = [sink for sink in sinks if sink not in headsets]

        # Delays need two speakers to mean anything, and a worn device has no flight time at all
        if not delay_enabled or len(speakers) < 2:
            return None

        positions = self.speaker_positions(settings)
        delays = source_delays(
            self.spatial_source,
            {sink: positions.get(sink, (0.0, 0.0)) for sink in speakers},
            room_size,
        )
        return [delays.get(sink, 0.0) for sink in sinks]

    def headset_sinks(self, available: list[dict] | None = None) -> set[str]:
        sinks = available if available is not None else self.list_sinks()

        return {sink["name"] for sink in sinks if sink.get("kind") == SinkKind.HEADSET}

    def spatial_gains(
        self,
        sinks: list[str] | None,
        available: list[dict] | None = None,
        settings: dict | None = None,
    ) -> list[list[float]] | None:
        if not self.spatial_enabled:
            return None

        source = self.spatial_source

        # The default output has no known position, so only left/right balance can apply to it
        if sinks is None:
            return [list(stereo_balance(source[0]))]

        per_sink = channel_gains(
            source,
            sinks,
            self.speaker_positions(settings),
            self.headset_sinks(available),
        )
        return [list(per_sink.get(sink, (1.0, 1.0))) for sink in sinks]

    def on_spatial_toggled(self, widget, new_value, old_value):
        # Guarded: the switch's value is loaded before the button row exists on the first build
        row = getattr(self, "spatial_button_row", None)
        if row is not None:
            row.set_sensitive(bool(new_value))

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

    def resolve_sinks(
        self, available: list[dict] | None = None, settings: dict | None = None
    ) -> list[str] | None:
        target = self.speakers

        if target in (Target.DEFAULT, Target.CUSTOM, ""):
            return None

        sinks = available if available is not None else self.list_sinks()
        return resolve_target(
            target, [sink["name"] for sink in sinks], self.speaker_groups(settings)
        )

    def speaker_items(self) -> list[IconComboRowItem]:
        lm = self.plugin_base.lm
        items = [
            IconComboRowItem(
                value=Target.DEFAULT.value,
                label=lm.get("action.play-sound.speakers.default"),
                icon_name=target_icon(Target.DEFAULT),
            ),
            IconComboRowItem(
                value=Target.ALL.value,
                label=lm.get("action.play-sound.speakers.all"),
                icon_name=target_icon(Target.ALL),
            ),
        ]

        items += [
            IconComboRowItem(
                value=format_sink_target(sink["name"]),
                label=sink["label"],
                icon_name=sink_icon(sink.get("kind", SinkKind.SPEAKER.value), sink.get("bluetooth", False)),
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
                value=Target.CUSTOM.value,
                label=lm.get("action.play-sound.speakers.custom"),
                icon_name=target_icon(Target.CUSTOM),
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
        # Checked first: with no sound server there are no sinks to be missing in the first place
        if not self.plugin_base.audio_server()["available"]:
            return self.plugin_base.lm.get("action.play-sound.speakers.no-server")

        available = [sink["name"] for sink in self.list_sinks()]
        absent = missing_sinks(self.speakers, available, self.speaker_groups())
        if not absent:
            return None

        return f"{self.plugin_base.lm.get('action.play-sound.speakers.missing')} {', '.join(absent)}"

    def on_speakers_change(self, widget, new_value, old_value):
        # ComboRow passes item objects here, not the stored strings
        if target_value(new_value) != Target.CUSTOM:
            return

        # "Custom..." acts as a button, so the previous selection is restored before opening the editor
        previous = target_value(old_value)
        previous = previous if previous and previous != Target.CUSTOM else Target.DEFAULT
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

    def action_tag(self) -> str:
        """Names every sound this action starts, and survives the action being recreated."""
        page = getattr(self.page, "json_path", "") or ""
        ident = getattr(self.input_ident, "json_identifier", "") or ""

        return f"{page}|{ident}|{self.state}|{self.action_id}"

    def loop_state(self) -> str:
        backend = getattr(self.plugin_base, "backend", None)
        if backend is None:
            return "stopped"

        try:
            return str(backend.playback_state(self.action_tag()))
        except Exception:  # rpyc reraises backend and connection faults as arbitrary types
            return "stopped"

    def pause_loop(self, paused: bool) -> None:
        backend = getattr(self.plugin_base, "backend", None)
        if backend is None:
            return

        try:
            backend.pause_tag(self.action_tag(), paused)
        except Exception:
            pass

    def stop_sounds(self, fade_out: float = 0.0) -> None:
        """Stops every sound this action started; a long one-shot outlives the action just as a loop does."""
        backend = getattr(self.plugin_base, "backend", None)
        if backend is None:
            return

        try:
            backend.stop_tag(self.action_tag(), fade_out)
        except Exception:
            pass

    def on_remove(self) -> None:
        # Nothing can reach these sounds once the action is gone, so none of them may outlive it
        self.stop_sounds()

    def on_removed_from_cache(self) -> None:
        # Clearing a key drops its actions without ever calling on_remove, and plain cache eviction
        # looks identical from here; the saved page is what tells them apart
        if not self.input_still_saved():
            self.stop_sounds()

        # Last, so a failure in the base teardown cannot leave the sound running
        super().on_removed_from_cache()

    def input_still_saved(self) -> bool:
        # An unreadable page counts as present: cutting a sound off wrongly is worse than a late stop
        try:
            inputs = self.page.dict[self.input_ident.input_type]

            return self.input_ident.json_identifier in inputs
        except Exception:
            return True

    def on_page_deleted(self, path) -> None:
        if path == getattr(self.page, "json_path", None):
            self.stop_sounds()

    def on_page_changed(self, controller, old_path, new_path) -> None:
        # Navigation only cuts off a held-open loop; a one-shot already fired is left to finish
        if self.mode is not Mode.PLAY_TILL_TURNED_OFF:
            return

        if self.keep_playing_off_page:
            return

        # Only this deck's page change matters, and only when the new page is not ours
        if controller is not getattr(self, "deck_controller", None):
            return
        if new_path == getattr(self.page, "json_path", None):
            return

        self.stop_sounds(self.fade_out)

    def _play(self, **kwargs):
        backend = getattr(self.plugin_base, "backend", None)
        handle = None
        path = self.picker.pick(self.sound_pool(), self.playback_order)

        if path is None:
            self.show_error(duration=2)
            return None

        if backend is not None:
            try:
                kwargs.setdefault("tag", self.action_tag())
                # Gathered once: a Default target with spatial off touches neither rpyc nor the disk
                needs_devices = self.spatial_enabled or self.speakers not in (
                    Target.DEFAULT,
                    Target.CUSTOM,
                    "",
                )
                available = self.list_sinks() if needs_devices else None
                settings = self.plugin_base.get_settings() if needs_devices else None

                sinks = self.resolve_sinks(available, settings)
                handle = backend.play(
                    path=path,
                    sinks=sinks,
                    volume=self.volume,
                    gains=self.spatial_gains(sinks, available, settings),
                    delays=self.spatial_delays(sinks, available, settings),
                    rate_scale=rate_scale(self.rate_variation),
                    **kwargs,
                )
            except Exception:
                handle = None

        if handle is None:
            self.show_error(duration=2)

        return handle

    def update_loop_option_visibility(self) -> None:
        # Only this mode can leave a loop running after the key is released
        relevant = self.mode is Mode.PLAY_TILL_TURNED_OFF

        for name in ("keep_playing_row", "pause_row"):
            row = getattr(self, name, None)
            if row is not None:
                row.widget.set_visible(relevant)

    def on_mode_change(self, widget, new_value, old_value):
        self.stop_sounds()
        self.active = False
        self.update_loop_option_visibility()

    def on_pressed(self, data) -> None:
        if not self.sound_pool():
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
                self.stop_sounds()
                self._play(loops=-1, fade_in=self.fade_in)

            case Mode.PLAY_TILL_TURNED_OFF:
                # Asked of the backend rather than remembered, so it survives recreation and restarts
                state = self.loop_state()

                if state == "stopped":
                    self._play(loops=-1, fade_in=self.fade_in)
                elif not self.pause_instead_of_stop:
                    self.stop_sounds(self.fade_out)
                else:
                    # Pause keeps the position, so the next press resumes where it left off
                    self.pause_loop(state == "playing")

    def on_released(self, data) -> None:
        if self.sound_pool() and Mode.RELEASE == self.mode:
            self._play(fade_in=self.fade_in, fade_out=self.fade_out)

        elif self.sound_pool() and self.mode == Mode.HOLD:
            self.stop_sounds(self.fade_out)
