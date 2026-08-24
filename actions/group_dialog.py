import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from collections.abc import Callable

from gi.repository import Adw, Gtk

from .audio_targets import delete_group, new_group_id, upsert_group


class SpeakerGroupDialog(Adw.Dialog):
    """Editor for speaker groups, which live in plugin settings and are shared by every action."""

    def __init__(
        self,
        plugin,
        sinks: list[dict],
        groups: list[dict],
        on_saved: Callable[[list[dict]], None],
    ):
        super().__init__()

        self.lm = plugin.lm
        self.sinks = sinks
        self.groups = groups
        self.on_saved = on_saved
        self.editing_id: str | None = None
        self.sink_switches: dict[str, Adw.SwitchRow] = {}

        self.set_title(self.lm.get("action.play-sound.groups.title"))
        self.set_content_width(520)
        self.set_content_height(620)

        self.group_list = Adw.PreferencesGroup(
            title=self.lm.get("action.play-sound.groups.existing")
        )

        self.name_row = Adw.EntryRow(title=self.lm.get("action.play-sound.groups.name"))
        self.editor = Adw.PreferencesGroup(
            title=self.lm.get("action.play-sound.groups.devices")
        )
        self.editor.add(self.name_row)

        for sink in self.sinks:
            switch = Adw.SwitchRow(title=sink["label"], subtitle=sink["name"])
            self.sink_switches[sink["name"]] = switch
            self.editor.add(switch)

        self.save_button = Gtk.Button(
            label=self.lm.get("action.play-sound.groups.save"),
            css_classes=["suggested-action"],
            margin_top=6,
        )
        self.save_button.connect("clicked", self.on_save)

        self.new_button = Gtk.Button(label=self.lm.get("action.play-sound.groups.new"))
        self.new_button.connect("clicked", lambda _button: self.load_group(None))

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        content.append(self.group_list)
        content.append(self.editor)
        content.append(self.save_button)
        content.append(self.new_button)

        header = Adw.HeaderBar()
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(Gtk.ScrolledWindow(child=content, propagate_natural_height=True))
        self.set_child(view)

        self.rebuild_group_list()

    def rebuild_group_list(self):
        for row in list(getattr(self, "group_rows", [])):
            self.group_list.remove(row)

        self.group_rows = []

        if not self.groups:
            empty = Adw.ActionRow(title=self.lm.get("action.play-sound.groups.empty"))
            empty.set_sensitive(False)
            self.group_list.add(empty)
            self.group_rows.append(empty)
            return

        for group in self.groups:
            row = Adw.ActionRow(
                title=group["name"],
                subtitle=self.describe_members(group),
                activatable=True,
            )
            row.connect("activated", self.on_row_activated, group["id"])

            remove = Gtk.Button(
                icon_name="user-trash-symbolic",
                valign=Gtk.Align.CENTER,
                css_classes=["flat"],
                tooltip_text=self.lm.get("action.play-sound.groups.delete"),
            )
            remove.connect("clicked", self.on_delete, group["id"])
            row.add_suffix(remove)

            self.group_list.add(row)
            self.group_rows.append(row)

    def describe_members(self, group: dict) -> str:
        labels = {sink["name"]: sink["label"] for sink in self.sinks}
        missing = self.lm.get("action.play-sound.speakers.unavailable")

        return ", ".join(labels.get(name, f"{name} {missing}") for name in group["sinks"])

    def load_group(self, group_id: str | None):
        self.editing_id = group_id
        group = next((g for g in self.groups if g["id"] == group_id), None)

        self.name_row.set_text(group["name"] if group else "")
        members = set(group["sinks"]) if group else set()

        for name, switch in self.sink_switches.items():
            switch.set_active(name in members)

    def on_row_activated(self, _row, group_id):
        self.load_group(group_id)

    def on_delete(self, _button, group_id):
        self.groups = delete_group(self.groups, group_id)
        if self.editing_id == group_id:
            self.load_group(None)

        self.commit()
        self.rebuild_group_list()

    def on_save(self, _button):
        name = self.name_row.get_text().strip()
        selected = [name_ for name_, switch in self.sink_switches.items() if switch.get_active()]

        # A disconnected member has no switch to read, so it is carried over instead of dropped
        editing = next((g for g in self.groups if g["id"] == self.editing_id), None)
        if editing is not None:
            selected += [s for s in editing["sinks"] if s not in self.sink_switches]

        # A group with no name or no devices could never be selected meaningfully, so it is not saved
        if not name or not selected:
            self.name_row.add_css_class("error")
            return

        self.name_row.remove_css_class("error")
        self.groups = upsert_group(
            self.groups, self.editing_id or new_group_id(), name, selected
        )

        self.commit()
        self.load_group(None)
        self.rebuild_group_list()

    def commit(self):
        self.on_saved([dict(group) for group in self.groups])
