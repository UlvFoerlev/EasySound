import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

# GstPlayFlags.AUDIO alone; stops playbin building a video sink for embedded cover art
AUDIO_ONLY = 0x00000002


class OutputError(Exception):
    pass


def _make(factory: str, name: str) -> Gst.Element:
    element = Gst.ElementFactory.make(factory, name)
    if element is None:
        raise OutputError(f"missing GStreamer element '{factory}'")

    return element


def _branch(bin_: Gst.Bin, index: int, device: str | None) -> tuple[Gst.Element, Gst.Element]:
    volume = _make("volume", f"volume_{index}")
    convert = _make("audioconvert", f"convert_{index}")
    sink = _make("pulsesink", f"sink_{index}")

    if device:
        sink.set_property("device", device)

    for element in (volume, convert, sink):
        bin_.add(element)

    if not volume.link(convert) or not convert.link(sink):
        raise OutputError("could not link output branch")

    return volume, sink


def build_output(devices: list[str | None]) -> tuple[Gst.Bin, list[Gst.Element]]:
    """Sink bin fanning one decoded stream out to every device; None means system default."""
    targets = devices or [None]
    bin_ = Gst.Bin.new("easysound-output")
    volumes: list[Gst.Element] = []

    if len(targets) == 1:
        volume, _ = _branch(bin_, 0, targets[0])
        volumes.append(volume)
        entry = volume.get_static_pad("sink")
    else:
        tee = _make("tee", "fanout")
        bin_.add(tee)

        for index, device in enumerate(targets):
            queue = _make("queue", f"queue_{index}")
            bin_.add(queue)

            volume, _ = _branch(bin_, index, device)
            volumes.append(volume)

            if not tee.link(queue) or not queue.link(volume):
                raise OutputError("could not link fanout branch")

        entry = tee.get_static_pad("sink")

    bin_.add_pad(Gst.GhostPad.new("sink", entry))

    return bin_, volumes
