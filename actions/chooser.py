import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gi.repository import Gio, GLib, Gtk

AUDIO_MIME_TYPES = (
    "audio/mpeg",
    "audio/x-wav",
    "audio/wav",
    "audio/vnd.wave",
    "audio/ogg",
    "audio/x-vorbis+ogg",
    "audio/flac",
    "audio/x-flac",
    "audio/x-opus+ogg",
)


def build_filter(filetypes: tuple[str, ...]) -> Gtk.FileFilter:
    audio_filter = Gtk.FileFilter()
    audio_filter.set_name("Audio Files")

    for t in filetypes:
        audio_filter.add_mime_type(t)

    return audio_filter


def build_filter_list(audio_filter: Gtk.FileFilter) -> Gio.ListStore:
    all_filter = Gtk.FileFilter()
    all_filter.set_name("All Files")
    all_filter.add_pattern("*")

    filter_list = Gio.ListStore.new(Gtk.FileFilter)
    filter_list.append(audio_filter)
    filter_list.append(all_filter)

    return filter_list


class ChooseFileDialog(Gtk.FileDialog):
    def __init__(
        self,
        plugin: Any,
        dialog_name: str = "File Chooser",
        setter_func: Callable | None = None,
        filetypes: tuple[str, ...] = AUDIO_MIME_TYPES,
    ):
        audio_filter = build_filter(filetypes=filetypes)

        super().__init__(
            title=dialog_name,
            accept_label=plugin.lm.get("action.generic.select"),
            filters=build_filter_list(audio_filter),
            default_filter=audio_filter,
        )

        self.selected_file = None
        self.setter_func = setter_func
        self.open(callback=self.callback)

    def callback(self, dialog, result):
        try:
            selected_file = self.open_finish(result)
        except GLib.Error:
            return

        path = selected_file.get_path() if selected_file else None
        if path is None:  # non-local locations have no filesystem path
            return

        self.selected_file = Path(path)
        if self.setter_func:
            self.setter_func(self.selected_file)
