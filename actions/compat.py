from gi.repository import Pango
from GtkHelper.GenerativeUI.FileDialogRow import FileDialogRow as _UpstreamFileDialogRow

# Bound the value label so a long path cannot squeeze the row title
FILE_LABEL_MAX_CHARS = 32


class FileDialogRow(_UpstreamFileDialogRow):
    """Upstream's FileDialogRow, with the abstract signal hooks supplied and its value label bounded."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # The label is hexpand with no ellipsizing, so its natural width wraps the title one char per line
        self.widget.file_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.widget.file_label.set_max_width_chars(FILE_LABEL_MAX_CHARS)

    def _file_changed(self, file):
        # A non-local location has no path; storing None makes load_from_path raise on the next open
        if file is None or file.get_path() is None:
            return

        super()._file_changed(file)

    # Upstream 1.5.0-beta.16 leaves both hooks abstract, which makes its own class impossible to instantiate
    def connect_signals(self):
        # The inner widget takes a plain python callback rather than a GObject signal
        self.widget._callback = self._file_changed

    def disconnect_signals(self):
        # set_ui_value calls load_from_path, which fires the callback, so suppressing it means detaching
        self.widget._callback = None
