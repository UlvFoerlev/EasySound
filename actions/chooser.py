import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Gio, GObject


# Import globals
import globals as gl


class FilterList(GObject.GObject, Gio.ListModel):
    pass


class ChooseFileDialog(Gtk.FileDialog):
    def __init__(
        self,
        dialog_name: str = "File Chooser",
        filetypes: list[str] = ["audio/mpeg", "audio/vnd.wav"],
    ):
        super().__init__(
            title=dialog_name,
            accept_label=gl.lm.get("action.generic.select"),
            filters=self.add_filters(filetypes=filetypes),
        )

        self.open(callback=self.callback)

        self.selected_file = None

    def callback(self, dialog, result):
        print("Callback")
        print(dialog)
        print(result)
        selected_file = result.return_value()
        print(selected_file)

        self.selected_file = selected_file

    def add_filters(self, filetypes: list[str]):
        filter_text = Gtk.FileFilter()

        filter_text.set_name("Audio Files")

        for t in filetypes:
            filter_text.add_mime_type(t)

        filter_list = Gtk.FilterListModel()
        filter_list.set_filter(filter_text)

        return filter_list
