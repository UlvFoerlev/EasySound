import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
from GtkHelper.ComboRow import SimpleComboRowItem


class IconComboRowItem(SimpleComboRowItem):
    """A combo item that also carries a symbolic icon name."""

    def __init__(self, value: str, label: str, icon_name: str | None = None):
        super().__init__(value=value, label=label)
        self.icon_name = icon_name


def _on_setup(_factory, list_item):
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    box.append(Gtk.Image())
    box.append(Gtk.Label(halign=Gtk.Align.START))
    list_item.set_child(box)


def _on_bind(_factory, list_item):
    box = list_item.get_child()
    image, label = box.get_first_child(), box.get_last_child()
    item = list_item.get_item()

    # Read defensively: an item built elsewhere has no icon, and must still render its text
    icon_name = getattr(item, "icon_name", None)
    image.set_visible(bool(icon_name))
    if icon_name:
        image.set_from_icon_name(icon_name)

    label.set_text(str(item))


def icon_factory() -> Gtk.SignalListItemFactory:
    """Replaces the framework's label-only factory; upstream's own items still render as plain text."""
    factory = Gtk.SignalListItemFactory()
    factory.connect("setup", _on_setup)
    factory.connect("bind", _on_bind)

    return factory
