import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import math
from collections.abc import Callable

from gi.repository import Adw, Gtk

from .spatial import (
    Side,
    MAX_ROOM_SIZE,
    MIN_ROOM_SIZE,
    clamp_room_size,
    clamp_unit,
    dbap_gains,
    default_emitter_position,
    default_layout,
    emitter_layout,
    emitters_for,
    listener_distances,
    source_delays,
)

CANVAS_SIZE = 420
HANDLE_RADIUS = 13.0
EAR_RADIUS = 10.0
PICK_RADIUS = 26.0
SOURCE_KEY = "\x00source"


class SpatialDialog(Adw.Dialog):
    """Top-down map: the listener sits at the centre, and every emitter and the source are draggable."""

    def __init__(
        self,
        plugin,
        sinks: list[str],
        labels: dict[str, str],
        positions: dict[str, tuple[float, float]],
        source: tuple[float, float],
        on_positions_changed: Callable[[dict[str, tuple[float, float]]], None],
        on_source_changed: Callable[[tuple[float, float]], None],
        room_size: float = 4.0,
        delay_enabled: bool = False,
        on_room_changed: Callable[[float, bool], None] | None = None,
        headsets: set[str] | None = None,
        on_headset_changed: Callable[[str, bool], None] | None = None,
    ):
        super().__init__()

        self.lm = plugin.lm
        self.sinks = list(sinks)
        self.labels = labels
        self.source = source
        self.on_positions_changed = on_positions_changed
        self.on_source_changed = on_source_changed
        self.on_room_changed = on_room_changed
        self.room_size = clamp_room_size(room_size)
        self.delay_enabled = bool(delay_enabled)
        # A headset is two emitters, one per ear, so its channels can be panned by geometry
        self.headsets = {sink for sink in (headsets or set()) if sink in self.sinks}
        self.dragging: str | None = None
        self.fg = (1.0, 1.0, 1.0)

        self.on_headset_changed = on_headset_changed
        self.saved = dict(positions)

        self.positions = emitter_layout(self.sinks, self.headsets, positions)
        self.ring_unplaced(positions)

        self.set_title(self.lm.get("action.play-sound.spatial.title"))
        self.set_content_width(CANVAS_SIZE + 60)
        self.set_content_height(CANVAS_SIZE + 260)

        self.canvas = Gtk.DrawingArea(hexpand=True, vexpand=True)
        self.canvas.set_size_request(CANVAS_SIZE, CANVAS_SIZE)
        self.canvas.set_draw_func(self.on_draw)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        drag.connect("drag-end", self.on_drag_end)
        self.canvas.add_controller(drag)

        self.hint_label = Gtk.Label(
            label=self.lm.get(self.hint_key()), wrap=True, css_classes=["dim-label"]
        )

        reset = Gtk.Button(label=self.lm.get("action.play-sound.spatial.reset"))
        reset.connect("clicked", self.on_reset)

        # Off by default: without a room size the distances are meaningless, and delays are a real risk
        self.delay_row = Adw.SwitchRow(
            title=self.lm.get("action.play-sound.spatial.delay"),
            subtitle=self.lm.get("action.play-sound.spatial.delay-subtitle"),
            active=self.delay_enabled,
        )
        self.delay_row.connect("notify::active", self.on_delay_toggled)

        self.room_row = Adw.SpinRow.new_with_range(MIN_ROOM_SIZE, MAX_ROOM_SIZE, 0.5)
        self.room_row.set_title(self.lm.get("action.play-sound.spatial.room"))
        self.room_row.set_subtitle(self.lm.get("action.play-sound.spatial.room-subtitle"))
        self.room_row.set_value(self.room_size)
        self.room_row.set_sensitive(self.delay_enabled)
        self.room_row.connect("changed", self.on_room_size_changed)

        settings_group = Adw.PreferencesGroup()
        settings_group.add(self.delay_row)
        settings_group.add(self.room_row)

        self.headset_group = Adw.PreferencesGroup(
            title=self.lm.get("action.play-sound.spatial.headset-group"),
            description=self.lm.get("action.play-sound.spatial.headset-group-subtitle"),
        )
        for sink in self.sinks:
            row = Adw.SwitchRow(
                title=self.labels.get(sink, sink), active=sink in self.headsets
            )
            row.connect("notify::active", self.on_headset_toggled, sink)
            self.headset_group.add(row)

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
        content.append(settings_group)
        if self.sinks:
            content.append(self.headset_group)
        content.append(reset)

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(Gtk.ScrolledWindow(child=content, propagate_natural_height=True))
        self.set_child(view)

    def ring_unplaced(self, saved: dict) -> None:
        # Speakers with no saved spot spread onto a ring instead of stacking on the listener
        unplaced = [
            sink for sink in self.sinks if sink not in self.headsets and sink not in saved
        ]
        self.positions.update(default_layout(unplaced))

    def on_headset_toggled(self, row, _param, sink: str) -> None:
        is_headset = row.get_active()
        if is_headset:
            self.headsets.add(sink)
        else:
            self.headsets.discard(sink)

        # A headset is two emitters and a speaker is one, so the map has to be rebuilt around it
        self.saved.update(self.positions)
        self.positions = emitter_layout(self.sinks, self.headsets, self.saved)
        self.ring_unplaced(self.saved)
        self.dragging = None

        if self.on_headset_changed is not None:
            self.on_headset_changed(sink, is_headset)
        self.on_positions_changed(dict(self.positions))

        self.hint_label.set_label(self.lm.get(self.hint_key()))
        self.canvas.queue_draw()

    def hint_key(self) -> str:
        if not self.sinks:
            return "action.play-sound.spatial.hint-default"
        if self.sinks and set(self.sinks) == self.headsets:
            return "action.play-sound.spatial.hint-headset"

        return "action.play-sound.spatial.hint"

    def emitter_label(self, emitter: str) -> str:
        sink, _, side = emitter.partition("#")
        label = self.labels.get(sink, sink)[:14]

        if side == Side.LEFT:
            return f"{label} [{self.lm.get('action.play-sound.spatial.left')}]"
        if side == Side.RIGHT:
            return f"{label} [{self.lm.get('action.play-sound.spatial.right')}]"

        return label

    def is_ear(self, emitter: str) -> bool:
        return "#" in emitter

    def speaker_emitters(self) -> dict[str, tuple[float, float]]:
        # Ears travel with the listener, so they are left out of room distances and delays
        return {
            emitter: point
            for emitter, point in self.positions.items()
            if not self.is_ear(emitter)
        }

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
        handles = dict(self.positions)
        handles[SOURCE_KEY] = self.source

        return handles

    def on_draw(self, area, cr, width, height, *_):
        cx, cy, scale = width / 2, height / 2, min(width, height) / 2 * 0.86
        # Taken from the widget so the map is legible in a light theme as well as a dark one
        fg = area.get_color()
        self.fg = (fg.red, fg.green, fg.blue)

        cr.set_source_rgba(*self.fg, 0.05)
        cr.arc(cx, cy, scale, 0, math.tau)
        cr.fill()

        cr.set_line_width(1.0)
        cr.set_source_rgba(*self.fg, 0.16)
        for fraction in (0.33, 0.66, 1.0):
            cr.arc(cx, cy, scale * fraction, 0, math.tau)
            cr.stroke()

        cr.move_to(cx - scale, cy)
        cr.line_to(cx + scale, cy)
        cr.move_to(cx, cy - scale)
        cr.line_to(cx, cy + scale)
        cr.stroke()

        cr.select_font_face("Sans")
        cr.set_font_size(11)

        # Fill brightness shows how much of the sound each emitter would carry
        gains = dbap_gains(self.source, self.positions)
        speakers = self.speaker_emitters()
        distances = listener_distances(speakers, self.room_size) if self.delay_enabled else {}
        delays = (
            source_delays(self.source, speakers, self.room_size) if self.delay_enabled else {}
        )

        if self.delay_enabled:
            for emitter, point in speakers.items():
                sx, sy = self.to_screen(point)
                self.draw_arrow(cr, cx, cy, sx, sy)
                self.draw_badge(cr, (cx + sx) / 2, (cy + sy) / 2, f"{distances.get(emitter, 0.0):.1f} m")

        for emitter, point in self.positions.items():
            sx, sy = self.to_screen(point)
            radius = EAR_RADIUS if self.is_ear(emitter) else HANDLE_RADIUS
            strength = gains.get(emitter, 0.0)

            cr.set_source_rgba(0.35, 0.75, 1.0, 0.25 + 0.65 * strength)
            cr.arc(sx, sy, radius, 0, math.tau)
            cr.fill()

            label = self.emitter_label(emitter)
            if self.delay_enabled and delays.get(emitter):
                label = f"{label}  +{delays[emitter] * 1000:.0f} ms"

            cr.set_source_rgba(*self.fg, 0.9)
            extents = cr.text_extents(label)
            cr.move_to(sx - extents.width / 2, sy + radius + 13)
            cr.show_text(label)

        cr.set_source_rgba(*self.fg, 0.6)
        cr.arc(cx, cy, 6, 0, math.tau)
        cr.fill()
        listener = self.lm.get("action.play-sound.spatial.listener")
        extents = cr.text_extents(listener)
        cr.set_source_rgba(*self.fg, 0.9)
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

        source_label = self.lm.get("action.play-sound.spatial.source")
        extents = cr.text_extents(source_label)
        cr.set_source_rgba(*self.fg, 0.9)
        cr.move_to(srx - extents.width / 2, sry + HANDLE_RADIUS + 12)
        cr.show_text(source_label)

    def draw_badge(self, cr, x, y, text):
        extents = cr.text_extents(text)

        inverse = tuple(1.0 - channel for channel in self.fg)
        cr.set_source_rgba(*inverse, 0.85)
        cr.rectangle(
            x - extents.width / 2 - 4, y - extents.height - 4, extents.width + 8, extents.height + 8
        )
        cr.fill()

        cr.set_source_rgba(*self.fg, 0.95)
        cr.move_to(x - extents.width / 2, y)
        cr.show_text(text)

    def draw_arrow(self, cr, from_x, from_y, to_x, to_y):
        angle = math.atan2(to_y - from_y, to_x - from_x)
        # Stop short of the dot so the head is not hidden underneath it
        tip_x = to_x - math.cos(angle) * (HANDLE_RADIUS + 2)
        tip_y = to_y - math.sin(angle) * (HANDLE_RADIUS + 2)
        head = 8.0
        spread = 0.4

        cr.set_source_rgba(*self.fg, 0.4)
        cr.set_line_width(1.5)
        cr.move_to(from_x, from_y)
        cr.line_to(tip_x, tip_y)
        cr.stroke()

        cr.move_to(tip_x, tip_y)
        cr.line_to(
            tip_x - math.cos(angle - spread) * head, tip_y - math.sin(angle - spread) * head
        )
        cr.line_to(
            tip_x - math.cos(angle + spread) * head, tip_y - math.sin(angle + spread) * head
        )
        cr.close_path()
        cr.fill()

    def on_delay_toggled(self, row, _param):
        self.delay_enabled = row.get_active()
        self.room_row.set_sensitive(self.delay_enabled)

        self.commit_room()
        self.canvas.queue_draw()

    def on_room_size_changed(self, row):
        self.room_size = clamp_room_size(row.get_value())

        self.commit_room()
        self.canvas.queue_draw()

    def commit_room(self):
        if self.on_room_changed is not None:
            self.on_room_changed(self.room_size, self.delay_enabled)

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
        self.source = (0.0, 0.0)
        self.on_source_changed(self.source)

        speakers = [sink for sink in self.sinks if sink not in self.headsets]
        self.positions = default_layout(speakers)
        for sink in self.headsets:
            for emitter in emitters_for(sink, True):
                self.positions[emitter] = default_emitter_position(emitter)

        if self.positions:
            self.on_positions_changed(dict(self.positions))

        self.canvas.queue_draw()
