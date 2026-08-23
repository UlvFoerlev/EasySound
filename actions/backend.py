from streamcontroller_plugin_tools import BackendBase
from pathlib import Path
from threading import Lock, Semaphore, Thread
import os
import time

import numpy as np
import pasimple
import pulsectl
import soundfile as sf

CHUNK_FRAMES = 1024
SINK_CACHE_SECONDS = 2.0
SAMPLE_WIDTH = 2
# How much audio may sit queued in the server; a stop cannot be quicker than this
BUFFER_SECONDS = 0.25
MAX_CONCURRENT_STREAMS = 32
SAMPLE_FORMAT = pasimple.PA_SAMPLE_S16LE
# How long a paused writer sleeps between checks; the server drains its own buffer meanwhile
PAUSE_POLL_SECONDS = 0.05

STOPPED = "stopped"
PLAYING = "playing"
PAUSED = "paused"


# Worn devices: placing them in a room makes no sense, so they are treated apart from speakers
HEADSET_HINTS = ("headset", "headphone", "earbud", "earphone", "hands-free")
# Duplicated on purpose: the frontend's SinkKind cannot be imported here, so a test asserts they agree
HEADSET = "headset"
SPEAKER = "speaker"


def sink_kind(proplist, active_port: str = "") -> str:
    """Best-effort device type; form factor is authoritative, the active port covers internal cards."""
    form_factor = (proplist.get("device.form_factor") or "").lower()
    if form_factor:
        return HEADSET if any(hint in form_factor for hint in HEADSET_HINTS) else SPEAKER

    # An internal card exposes headphones as a port of the same sink rather than as its own sink
    haystack = f"{active_port} {proplist.get('device.icon_name') or ''}".lower()

    return HEADSET if any(hint in haystack for hint in HEADSET_HINTS) else SPEAKER


def is_bluetooth(proplist, sink_name: str = "") -> bool:
    # bluez names the sink after the adapter, which is a reliable fallback when the bus is unset
    if (proplist.get("device.bus") or "").lower() == "bluetooth":
        return True

    return sink_name.startswith("bluez_")


def channel_weights(channel_gain: list[float] | None, channels: int):
    """Spreads a left/right spatial gain across a sound's actual channel count."""
    if not channel_gain:
        return np.ones(channels, dtype=np.float32)

    values = np.asarray(channel_gain, dtype=np.float32)

    if len(values) == channels:
        return values

    # A mono sound has no sides to pan, so the pair collapses into one gain
    if channels == 1:
        return np.array([values.mean()], dtype=np.float32)

    return np.resize(values, channels).astype(np.float32)


def file_stamp(path: str) -> tuple[float, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None

    return stat.st_mtime, stat.st_size


class Playback:
    """One logical sound, fanned out over one stream per target sink."""

    def __init__(self, tag: str = ""):
        # A caller-supplied identity, so a recreated action can still find the loop it started
        self.tag = tag
        self.stopping = False
        self.paused = False
        self.stop_fade_out = 0.0
        self.writers = 0


class Backend(BackendBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.cache: dict[str, tuple[np.ndarray, int, int]] = {}
        self.cache_stamps: dict[str, tuple[float, int] | None] = {}
        self.playbacks: dict[str, Playback] = {}
        self.lock = Lock()
        self.handle_counter = 0
        # Daemon threads rather than a ThreadPoolExecutor, so an endless loop cannot block process exit
        self.stream_slots = Semaphore(MAX_CONCURRENT_STREAMS)
        self.sink_cache: list[dict] = []
        self.sink_cache_time = 0.0

    def audio_server(self) -> dict:
        """Whether a PulseAudio-compatible server is reachable; PipeWire answers through its pulse layer."""
        try:
            with pulsectl.Pulse("easysound-server-probe") as pulse:
                info = pulse.server_info()
                name = getattr(info, "server_name", "") or ""

                return {"available": True, "name": str(name), "error": ""}
        except Exception as error:
            return {"available": False, "name": "", "error": str(error)}

    def list_sinks(self) -> list[dict]:
        # Briefly cached so a group or single-sink press does not pay a pulse round trip every time
        now = time.monotonic()
        if self.sink_cache and now - self.sink_cache_time < SINK_CACHE_SECONDS:
            return self.sink_cache

        sinks = self._query_sinks()
        if sinks:
            self.sink_cache = sinks
            self.sink_cache_time = now

        return sinks

    def _query_sinks(self) -> list[dict]:
        # sink.name is the identity: it is what pasimple's device_name expects
        try:
            with pulsectl.Pulse("easysound-sinks") as pulse:
                default_name = pulse.server_info().default_sink_name
                sinks = []

                for sink in pulse.sink_list():
                    props = sink.proplist
                    label = (
                        props.get("device.product.name")
                        or props.get("device.nick")
                        or props.get("device.description")
                        or sink.description
                        or sink.name
                    )
                    active_port = getattr(getattr(sink, "port_active", None), "name", "") or ""
                    sinks.append(
                        {
                            "name": sink.name,
                            "label": label,
                            "is_default": sink.name == default_name,
                            "kind": sink_kind(props, active_port),
                            "bluetooth": is_bluetooth(props, sink.name),
                        }
                    )

                return sinks
        except Exception:
            return []

    def preload_sound(self, path: str | Path, force: bool = False) -> bool:
        key = path if isinstance(path, str) else str(path)
        stamp = file_stamp(key)

        # A cached sound is reused unless the file changed on disk, so a press never waits on decoding
        if not force and key in self.cache and self.cache_stamps.get(key) == stamp:
            return True

        try:
            samples, rate = sf.read(key, dtype="int16", always_2d=True)
        except Exception:
            self.cache.pop(key, None)
            self.cache_stamps.pop(key, None)
            return False

        self.cache[key] = (samples, int(rate), samples.shape[1])
        self.cache_stamps[key] = stamp
        return True

    def warm_sound(self, path: str | Path) -> None:
        # Fire-and-forget so page loads and key presses never block on the first decode
        Thread(target=self.preload_sound, args=(path,), daemon=True).start()

    def play(
        self,
        path: str | Path,
        sinks: list[str] | None = None,
        volume: float = 100.0,
        loops: int = 0,
        fade_in: float = 0.0,
        fade_out: float = 0.0,
        gains: list[list[float]] | None = None,
        delays: list[float] | None = None,
        rate_scale: float = 1.0,
        tag: str = "",
    ) -> str | None:
        key = path if isinstance(path, str) else str(path)

        if not self.preload_sound(path=key):
            return None

        sound = self.cache[key]
        _, rate, channels = sound

        # Playing the same samples at another rate shifts pitch and speed together
        rate = max(int(rate * max(rate_scale, 0.1)), 1000)
        # A mono sound has no sides to pan, so spatial playback upmixes it to stereo first
        play_channels = 2 if gains and channels == 1 else channels

        # None means "whatever the server considers default", which is one stream, not zero
        targets = [None] if sinks is None else list(sinks)
        if not targets:
            return None

        # Spatial gains arrive parallel to targets, so a stream that fails to open drops its entry too
        opened = []
        for index, sink in enumerate(targets):
            stream = self._open_stream(sink=sink, rate=rate, channels=play_channels)
            if stream is not None:
                channel_gain = gains[index] if gains and index < len(gains) else None
                delay = delays[index] if delays and index < len(delays) else 0.0
                opened.append((stream, channel_weights(channel_gain, play_channels), delay))

        # A partial fan-out still counts as playing: one dead speaker must not fail the whole group
        if not opened:
            return None

        gain = max(min(volume / 100.0, 1.0), 0.0)
        playback = Playback(tag=tag)

        with self.lock:
            self.handle_counter += 1
            handle = f"playback-{self.handle_counter}"
            self.playbacks[handle] = playback
            playback.writers = len(opened)

        for stream, weights, delay in opened:
            Thread(
                target=self._pump,
                args=(
                    handle,
                    playback,
                    stream,
                    weights,
                    delay,
                    play_channels,
                    rate,
                    sound,
                    gain,
                    loops,
                    fade_in,
                    fade_out,
                ),
                daemon=True,
            ).start()

        return handle

    def stop(self, handle: str, fade_out: float = 0.0) -> None:
        with self.lock:
            playback = self.playbacks.get(handle)

        if playback is None:
            return

        playback.stop_fade_out = max(fade_out, 0.0)
        playback.stopping = True

    def stop_all(self, fade_out: float = 0.0) -> int:
        with self.lock:
            playbacks = list(self.playbacks.values())

        for playback in playbacks:
            playback.stop_fade_out = max(fade_out, 0.0)
            playback.stopping = True

        return len(playbacks)

    def is_playing(self, tag: str) -> bool:
        """Authoritative on/off state: it survives the action being recreated or the app restarting."""
        if not tag:
            return False

        with self.lock:
            return any(
                playback.tag == tag and not playback.stopping
                for playback in self.playbacks.values()
            )

    def playback_state(self, tag: str) -> str:
        """One of stopped, playing or paused, so a button can be a three-state toggle."""
        if not tag:
            return STOPPED

        with self.lock:
            live = [
                playback
                for playback in self.playbacks.values()
                if playback.tag == tag and not playback.stopping
            ]

        if not live:
            return STOPPED

        return PAUSED if all(playback.paused for playback in live) else PLAYING

    def pause_tag(self, tag: str, paused: bool = True) -> int:
        if not tag:
            return 0

        with self.lock:
            tagged = [p for p in self.playbacks.values() if p.tag == tag and not p.stopping]

        for playback in tagged:
            playback.paused = bool(paused)

        return len(tagged)

    def stop_tag(self, tag: str, fade_out: float = 0.0) -> int:
        if not tag:
            return 0

        with self.lock:
            tagged = [p for p in self.playbacks.values() if p.tag == tag]

        for playback in tagged:
            playback.stop_fade_out = max(fade_out, 0.0)
            playback.stopping = True

        return len(tagged)

    def _open_stream(self, sink: str | None, rate: int, channels: int):
        if not self.stream_slots.acquire(blocking=False):
            return None

        try:
            return pasimple.PaSimple(
                pasimple.PA_STREAM_PLAYBACK,
                SAMPLE_FORMAT,
                channels,
                rate,
                app_name="EasySound",
                stream_name="EasySound",
                device_name=sink,
                # Default buffering is about 2 s, which would make a stop that late and delay fades
                tlength=int(rate * channels * SAMPLE_WIDTH * BUFFER_SECONDS),
            )
        except Exception:
            self.stream_slots.release()
            return None

    def _pump(
        self,
        handle: str,
        playback: Playback,
        stream,
        weights,
        delay: float,
        play_channels: int,
        rate: int,
        sound: tuple,
        gain: float,
        loops: int,
        fade_in: float,
        fade_out: float,
    ) -> None:
        try:
            # Passed in rather than re-read: the cache entry can be replaced while this thread runs
            samples, _, channels = sound
            total = len(samples)

            # Wavefront delay: silence written up front, so this speaker starts late by that much
            pad = int(max(delay, 0.0) * rate)
            if pad:
                stream.write(np.zeros((pad, play_channels), dtype=np.int16).tobytes())
            fade_in_frames = int(fade_in * rate)
            fade_out_frames = int(fade_out * rate)

            position = 0
            played = 0
            remaining_loops = loops
            stop_at = None

            while total:
                # Held here rather than closed: the position is kept so a resume is seamless, and
                # what the server has already buffered plays out as the tail
                while playback.paused and not playback.stopping:
                    time.sleep(PAUSE_POLL_SECONDS)

                if playback.stopping and stop_at is None:
                    stop_at = played
                    stop_frames = int(playback.stop_fade_out * rate)
                    if stop_frames <= 0:
                        break

                if position >= total:
                    if remaining_loops == 0:
                        break
                    if remaining_loops > 0:
                        remaining_loops -= 1
                    position = 0

                count = min(CHUNK_FRAMES, total - position)
                frames = np.arange(played, played + count, dtype=np.float32)
                envelope = np.ones(count, dtype=np.float32)

                if fade_in_frames > 0:
                    envelope *= np.clip(frames / fade_in_frames, 0.0, 1.0)

                # A looping sound has no natural end, so its fade-out only happens on stop
                if fade_out_frames > 0 and loops == 0:
                    envelope *= np.clip((total - frames) / fade_out_frames, 0.0, 1.0)

                if stop_at is not None:
                    stop_frames = max(int(playback.stop_fade_out * rate), 1)
                    envelope *= np.clip(1.0 - (frames - stop_at) / stop_frames, 0.0, 1.0)

                chunk = samples[position : position + count].astype(np.float32)
                if play_channels != channels:
                    chunk = np.repeat(chunk, play_channels // channels, axis=1)

                shaped = chunk * (gain * envelope)[:, None] * weights
                stream.write(shaped.astype(np.int16).tobytes())

                position += count
                played += count

                if stop_at is not None and played - stop_at >= max(int(playback.stop_fade_out * rate), 1):
                    break

            try:
                # A stop discards what is still queued; a sound that ended naturally plays its tail out
                if stop_at is not None:
                    stream.flush()
                else:
                    stream.drain()
            except Exception:
                pass
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

            self.stream_slots.release()

            with self.lock:
                playback.writers -= 1
                if playback.writers <= 0:
                    self.playbacks.pop(handle, None)


backend = Backend()
