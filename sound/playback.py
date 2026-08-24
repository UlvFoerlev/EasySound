from collections.abc import Callable

import gi

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

from .envelope import Envelope
from .output import AUDIO_ONLY, OutputError, build_output

SEEK_FLAGS = Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT


class SoundPipeline:
    """A pooled playbin kept prerolled in PAUSED so starting it costs a state change."""

    def __init__(self, path: str, devices: list[str | None], on_idle: Callable[["SoundPipeline"], None]):
        self.path = path
        self.on_idle = on_idle
        self.failed = False
        self.playing = False

        # Guards against parking twice when a natural end and an explicit stop race
        self.parked = True

        # Bumped on every start so stale handles cannot act on a recycled pipeline
        self.token = 0
        self._loops_left = 0

        self.pipeline = Gst.ElementFactory.make("playbin3", None)
        if self.pipeline is None:
            raise OutputError("missing GStreamer element 'playbin3'")

        output, volumes = build_output(devices)

        self.pipeline.set_property("uri", Gst.filename_to_uri(path))
        self.pipeline.set_property("flags", AUDIO_ONLY)
        self.pipeline.set_property("audio-sink", output)

        self.envelope = Envelope(volumes)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_message)

    def arm(self) -> None:
        self.pipeline.set_state(Gst.State.PAUSED)

    def wait_ready(self, timeout_ms: int) -> bool:
        result, state, _ = self.pipeline.get_state(timeout_ms * Gst.MSECOND)

        if result == Gst.StateChangeReturn.FAILURE:
            self.failed = True
            return False

        return state in (Gst.State.PAUSED, Gst.State.PLAYING)

    def duration(self) -> int | None:
        known, value = self.pipeline.query_duration(Gst.Format.TIME)
        return value if known and value > 0 else None

    def position(self) -> int:
        known, value = self.pipeline.query_position(Gst.Format.TIME)
        return value if known else 0

    def start(self, gain: float, loops: int, fade_in: float, fade_out: float) -> int:
        self.token += 1
        self._loops_left = loops
        self.playing = True
        self.parked = False

        self.pipeline.seek_simple(Gst.Format.TIME, SEEK_FLAGS, 0)
        self.envelope.apply(gain, fade_in, fade_out, None if loops else self.duration())
        self.pipeline.set_state(Gst.State.PLAYING)

        return self.token

    def stop(self, token: int | None = None) -> None:
        if token is not None and token != self.token:
            return

        if self.parked:
            return

        self.parked = True
        self.playing = False
        self._loops_left = 0

        self.pipeline.set_state(Gst.State.PAUSED)
        self.envelope.hold()
        self.pipeline.seek_simple(Gst.Format.TIME, SEEK_FLAGS, 0)

        self.on_idle(self)

    def fade_out(self, fade: float, token: int | None = None) -> None:
        if token is not None and token != self.token:
            return

        if not self.playing or not fade:
            self.stop(token)
            return

        self._loops_left = 0
        self.envelope.release(fade, self.position())
        GLib.timeout_add(int(fade * 1000), self._finish_fade, self.token)

    def _finish_fade(self, token: int) -> bool:
        self.stop(token)
        return GLib.SOURCE_REMOVE

    def dispose(self) -> None:
        self.playing = False
        self.parked = True
        bus = self.pipeline.get_bus()
        bus.remove_signal_watch()
        self.pipeline.set_state(Gst.State.NULL)

    def _on_message(self, _bus: Gst.Bus, message: Gst.Message) -> bool:
        if message.type == Gst.MessageType.ERROR:
            self.failed = True
            self.playing = False
            self.pipeline.set_state(Gst.State.NULL)

            if not self.parked:
                self.parked = True
                self.on_idle(self)
        elif message.type == Gst.MessageType.EOS:
            self._on_finished()

        return True

    def _on_finished(self) -> None:
        if self.parked:
            return

        if self._loops_left == 0:
            self.stop()
            return

        if self._loops_left > 0:
            self._loops_left -= 1

        # A loop restart replays stream time, so freeze the gain rather than fade in again
        self.envelope.hold()
        self.pipeline.seek_simple(Gst.Format.TIME, SEEK_FLAGS, 0)


class Playback:
    """Handle on one started sound, valid only until its pipeline is recycled."""

    def __init__(self, pipeline: SoundPipeline, token: int):
        self._pipeline = pipeline
        self._token = token

    @property
    def active(self) -> bool:
        return self._pipeline.playing and self._pipeline.token == self._token

    def stop(self) -> None:
        self._pipeline.stop(self._token)

    def fadeout(self, seconds: float) -> None:
        self._pipeline.fade_out(seconds, self._token)
