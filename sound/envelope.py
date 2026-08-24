import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstController", "1.0")
from gi.repository import Gst, GstController

MAX_GAIN = 1.0


def to_gain(volume: float) -> float:
    return max(min(volume / 100.0, MAX_GAIN), 0.0)


class Envelope:
    """Volume automation applied in lockstep to every output branch."""

    def __init__(self, volumes: list[Gst.Element]):
        self.volumes = volumes
        self.gain = MAX_GAIN
        self._sources: dict[Gst.Element, GstController.InterpolationControlSource] = {}
        self._bindings: dict[Gst.Element, GstController.ControlBinding] = {}

    def _source(self, element: Gst.Element) -> GstController.InterpolationControlSource:
        source = self._sources.get(element)
        if source is not None:
            return source

        source = GstController.InterpolationControlSource()
        source.set_property("mode", GstController.InterpolationMode.LINEAR)
        binding = GstController.DirectControlBinding.new_absolute(element, "volume", source)
        element.add_control_binding(binding)

        self._sources[element] = source
        self._bindings[element] = binding

        return source

    def hold(self, gain: float | None = None) -> None:
        """Drop automation and sit at a fixed gain."""
        if gain is not None:
            self.gain = gain

        for element in self.volumes:
            binding = self._bindings.pop(element, None)
            if binding is not None:
                element.remove_control_binding(binding)
                self._sources.pop(element, None)

            element.set_property("volume", self.gain)

    def apply(self, gain: float, fade_in: float, fade_out: float, duration: int | None) -> None:
        self.gain = gain

        if not fade_in and not fade_out:
            self.hold()
            return

        peak_at = int(fade_in * Gst.SECOND)
        tail_at = None

        if fade_out and duration:
            tail_at = max(duration - int(fade_out * Gst.SECOND), peak_at)

        for element in self.volumes:
            source = self._source(element)
            source.unset_all()

            if fade_in:
                source.set(0, 0.0)

            source.set(peak_at, gain)

            if tail_at is not None:
                source.set(tail_at, gain)
                source.set(max(duration, tail_at + 1), 0.0)

    def release(self, fade: float, position: int) -> None:
        """Ramp to silence from wherever playback currently is."""
        if not fade:
            self.hold(0.0)
            return

        end = position + int(fade * Gst.SECOND)

        for element in self.volumes:
            source = self._source(element)
            source.unset_all()
            source.set(position, self.gain)
            source.set(end, 0.0)
