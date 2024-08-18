import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from pathlib import Path
from typing import Any

# Import globals
import globals as gl
from gi.repository import Gio, GLib, GObject, Gtk
from collections.abc import Callable


class FilterList(GObject.GObject, Gio.ListModel):
    pass


class ChooseFileDialog(Gtk.FileDialog):
    def __init__(
        self,
        plugin: Any,
        dialog_name: str = "File Chooser",
        setter_func: Callable | None = None,
        start_path: Path | None = None,
        filetypes: list[str] = ["audio/mpeg", "audio/vnd.wav"],
    ):
        super().__init__(
            title=dialog_name,
            accept_label=plugin.lm.get("action.generic.select"),
            # filters=self.add_filters(filetypes=filetypes),
        )

        if start_path:
            self.set_current_folder(str(start_path))

        self.selected_file = None
        self.setter_func = setter_func
        self.open(callback=self.callback)

    def callback(self, dialog, result):
        selected_file = self.open_finish(result)

        self.selected_file = Path(selected_file.get_path())
        if self.setter_func:
            self.setter_func(self.selected_file)

    def add_filters(self, filetypes: list[str]):
        filter_text = Gtk.FileFilter()

        filter_text.set_name("Audio Files")

        for t in filetypes:
            filter_text.add_mime_type(t)

        filter_list = Gtk.FilterListModel()
        filter_list.set_filter(filter_text)

        return filter_list
