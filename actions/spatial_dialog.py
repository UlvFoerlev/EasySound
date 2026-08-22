import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import math
from collections.abc import Callable

from gi.repository import Adw, Gtk

from .spatial import channel_gains, clamp_unit, default_layout

CANVAS_SIZE = 420
HANDLE_RADIUS = 13.0
PICK_RADIUS = 30.0
SOURCE_KEY = "\x00source"


class SpatialDialog(Adw.Dialog):
    """Top-down map: the listener sits at the centre, speakers and the sound source are draggable."""

    def __init__(
        self,
        plugin,
        sinks: list[str],
        labels: dict[str, str],
        positions: dict[str, tuple[float, float]],
        source: tuple[float, float],
        on_positions_changed: Callable[[dict[str, tuple[float, float]]], None],
        on_source_changed: Callable[[tuple[float, float]], None],
    ):
        super().__init__()

        self.lm = plugin.lm
        self.sinks = list(sinks)
        self.labels = labels
        self.source = source
        self.on_positions_changed = on_positions_changed
        self.on_source_changed = on_source_changed
        self.dragging: str | None = None

        # Speakers without a saved spot start on a ring rather than stacked on the listener
        ring = default_layout([sink for sink in self.sinks if sink not in positions])
        self.positions = {
            sink: positions.get(sink, ring.get(sink, (0.0, 0.0))) for sink in self.sinks
        }

        self.set_title(self.lm.get("action.play-sound.spatial.title"))
        self.set_content_width(CANVAS_SIZE + 60)
        self.set_content_height(CANVAS_SIZE + 190)

        self.canvas = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.canvas.set_size_request(CANVAS_SIZE, CANVAS_SIZE)
        self.canvas.set_draw_func(self.on_draw)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        self.canvas.add_controller(drag)

        hint = self.lm.get(
            "action.play-sound.spatial.hint"
            if self.sinks
            else "action.play-sound.spatial.hint-default"
        )
        self.hint_label = Gtk.Label(label=hint, wrap=True, css_classes=["dim-label"])

        reset = Gtk.Button(label=self.lm.get("action.play-sound.spatial.reset"))
        reset.connect("clicked", self.on_reset)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        content.append(self.canvas)
        content.append(self.hint_label)
        content.append(reset)

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(content)
        self.set_child(view)

    def geometry(self) -> tuple[float, float, float]:
        width = self.canvas.get_width() or CANVAS_SIZE
        height = self.canvas.get_height() or CANVAS_SIZE

        return width / 2, height / 2, min(width, height) / 2 * 0.86

    def to_screen(self, point: tuple[float, float]) -> tuple[float, float]:
        cx, cy, scale = self.geometry()

        # Screen y grows downward, so front-of-listener is negated
        return cx + point[0] * scale, cy - point[1] * scale

    def to_unit(self, x: float, y: float) -> tuple[float, float]:
        cx, cy, scale = self.geometry()

        return clamp_unit((x - cx) / scale), clamp_unit(-(y - cy) / scale)

    def handles(self) -> dict[str, tuple[float, float]]:
        handles = {sink: self.positions[sink] for sink in self.sinks}
        handles[SOURCE_KEY] = self.source

        return handles

    def on_draw(self, area, cr, width, height, *_):
        cx, cy, scale = width / 2, height / 2, min(width, height) / 2 * 0.86

        cr.set_source_rgba(1, 1, 1, 0.04)
        cr.arc(cx, cy, scale, 0, math.tau)
        cr.fill()

        cr.set_line_width(1.0)
        cr.set_source_rgba(1, 1, 1, 0.12)
        for fraction in (0.33, 0.66, 1.0):
            cr.arc(cx, cy, scale * fraction, 0, math.tau)
            cr.stroke()

        cr.move_to(cx - scale, cy)
        cr.line_to(cx + scale, cy)
        cr.move_to(cx, cy - scale)
        cr.line_to(cx, cy + scale)
        cr.stroke()

        # Gain feedback: a speaker's fill shows how much of this sound it would carry
        gains = channel_gains(self.source, self.sinks, self.positions)

        for sink in self.sinks:
            sx, sy = self.to_screen(self.positions[sink])
            left, right = gains.get(sink, (0.0, 0.0))
            strength = max(left, right)

            cr.set_source_rgba(0.35, 0.75, 1.0, 0.25 + 0.65 * strength)
            cr.arc(sx, sy, HANDLE_RADIUS, 0, math.tau)
            cr.fill()

            cr.set_source_rgba(1, 1, 1, 0.85)
            cr.select_font_face("Sans")
            cr.set_font_size(11)
            label = self.labels.get(sink, sink)[:14]
            extents = cr.text_extents(label)
            cr.move_to(sx - extents.width / 2, sy + HANDLE_RADIUS + 14)
            cr.show_text(label)

        cr.set_source_rgba(1, 1, 1, 0.55)
        cr.arc(cx, cy, 6, 0, math.tau)
        cr.fill()
        listener = self.lm.get("action.play-sound.spatial.listener")
        extents = cr.text_extents(listener)
        cr.move_to(cx - extents.width / 2, cy + 22)
        cr.show_text(listener)

        srx, sry = self.to_screen(self.source)
        cr.set_source_rgba(1.0, 0.62, 0.2, 0.95)
        cr.arc(srx, sry, HANDLE_RADIUS - 2, 0, math.tau)
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.set_line_width(2.0)
        cr.arc(srx, sry, HANDLE_RADIUS - 2, 0, math.tau)
        cr.stroke()

    def on_drag_begin(self, gesture, start_x, start_y):
        self.dragging = None
        nearest = PICK_RADIUS

        for key, point in self.handles().items():
            hx, hy = self.to_screen(point)
            distance = math.hypot(hx - start_x, hy - start_y)
            if distance <= nearest:
                nearest = distance
                self.dragging = key

    def on_drag_update(self, gesture, offset_x, offset_y):
        if self.dragging is None:
            return

        ok, start_x, start_y = gesture.get_start_point()
        if not ok:
            return

        point = self.to_unit(start_x + offset_x, start_y + offset_y)
        if self.dragging == SOURCE_KEY:
            self.source = point
        else:
            self.positions[self.dragging] = point

        self.canvas.queue_draw()

    def on_drag_end(self, gesture, offset_x, offset_y):
        if self.dragging is None:
            return

        if self.dragging == SOURCE_KEY:
            self.on_source_changed(self.source)
        else:
            self.on_positions_changed(dict(self.positions))

        self.dragging = None

    def on_reset(self, _button):
        self.positions = default_layout(self.sinks)
        self.source = (0.0, 0.0)

        self.on_positions_changed(dict(self.positions))
        self.on_source_changed(self.source)
        self.canvas.queue_draw()
