import importlib.util
import sys
import threading
import time
import types

import pytest

from conftest import REPO_ROOT

# pulsectl loads libpulse at import time, which is not an ImportError, so any failure skips
try:
    import numpy  # noqa: F401
    import pasimple  # noqa: F401
    import pulsectl  # noqa: F401
    import soundfile  # noqa: F401
except Exception as exc:  # pragma: no cover
    pytest.skip(f"audio engine deps unavailable: {exc}", allow_module_level=True)

import numpy as np
import soundfile as sf

RATE = 8000
CHANNELS = 2


@pytest.fixture(scope="module")
def backend_module():
    # BackendBase would try to connect back over rpyc, so it is stubbed to load the module in isolation
    stub = types.ModuleType("streamcontroller_plugin_tools")

    class BackendBase:
        def __init__(self, *args, **kwargs):
            pass

    stub.BackendBase = BackendBase
    saved = sys.modules.get("streamcontroller_plugin_tools")
    sys.modules["streamcontroller_plugin_tools"] = stub

    spec = importlib.util.spec_from_file_location(
        "easysound_backend_under_test", REPO_ROOT / "actions" / "backend.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    yield module

    if saved is None:
        sys.modules.pop("streamcontroller_plugin_tools", None)
    else:
        sys.modules["streamcontroller_plugin_tools"] = saved


@pytest.fixture
def backend(backend_module):
    return backend_module.Backend()


class FakeStream:
    def __init__(self):
        self.payload = bytearray()
        self.closed = False
        self.drained = False
        self.flushed = False

    def write(self, data):
        self.payload += data

    def drain(self):
        self.drained = True

    def flush(self):
        self.flushed = True

    def close(self):
        self.closed = True


@pytest.fixture
def fake_streams(backend, monkeypatch):
    created = []

    def _open(sink, rate, channels):
        stream = FakeStream()
        stream.sink = sink
        created.append(stream)
        return stream

    monkeypatch.setattr(backend, "_open_stream", _open)
    return created


def write_tone(path, seconds=0.25, value=8000):
    frames = int(RATE * seconds)
    samples = np.full((frames, CHANNELS), value, dtype=np.int16)
    sf.write(str(path), samples, RATE, subtype="PCM_16")
    return frames


def as_samples(stream):
    return np.frombuffer(bytes(stream.payload), dtype=np.int16).reshape(-1, CHANNELS)


def wait_for_idle(backend, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not backend.playbacks:
            return True
        time.sleep(0.01)
    return False


def test_preload_caches_and_reports_success(backend, tmp_path):
    path = tmp_path / "tone.wav"
    write_tone(path)

    assert backend.preload_sound(str(path)) is True
    assert str(path) in backend.cache


def test_preload_rejects_a_non_audio_file(backend, tmp_path):
    path = tmp_path / "junk.wav"
    path.write_text("not audio")

    assert backend.preload_sound(str(path)) is False
    assert str(path) not in backend.cache


def test_preload_reuses_the_cache(backend, tmp_path):
    path = tmp_path / "tone.wav"
    write_tone(path)
    backend.preload_sound(str(path))
    first = backend.cache[str(path)][0]

    backend.preload_sound(str(path))
    assert backend.cache[str(path)][0] is first


def test_preload_redecodes_a_changed_file(backend, tmp_path):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.1)
    backend.preload_sound(str(path))
    first = backend.cache[str(path)][0]

    write_tone(path, seconds=0.2)
    backend.cache_stamps[str(path)] = (0.0, 0)  # stand in for a differing mtime/size
    backend.preload_sound(str(path))

    assert backend.cache[str(path)][0] is not first


def test_play_returns_none_for_an_unloadable_file(backend, tmp_path):
    assert backend.play(str(tmp_path / "missing.wav")) is None


def test_play_returns_none_when_no_sink_resolves(backend, tmp_path):
    path = tmp_path / "tone.wav"
    write_tone(path)

    # An empty target list means every member was absent, which must not silently play on the default
    assert backend.play(str(path), sinks=[]) is None


def test_one_shot_writes_the_whole_sound_once(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    frames = write_tone(path, seconds=0.2)

    handle = backend.play(str(path), sinks=["sink-a"])
    assert handle is not None
    assert wait_for_idle(backend)

    assert len(fake_streams) == 1
    assert len(as_samples(fake_streams[0])) == frames
    assert fake_streams[0].closed is True


def test_a_group_fans_out_one_stream_per_sink(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    frames = write_tone(path, seconds=0.1)

    backend.play(str(path), sinks=["sink-a", "sink-b", "sink-c"])
    assert wait_for_idle(backend)

    assert sorted(s.sink for s in fake_streams) == ["sink-a", "sink-b", "sink-c"]
    for stream in fake_streams:
        assert len(as_samples(stream)) == frames


def test_a_failing_sink_does_not_stop_the_others(backend, tmp_path, monkeypatch):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.1)
    good = FakeStream()

    def _open(sink, rate, channels):
        return None if sink == "broken" else good

    monkeypatch.setattr(backend, "_open_stream", _open)

    assert backend.play(str(path), sinks=["broken", "works"]) is not None
    assert wait_for_idle(backend)
    assert len(good.payload) > 0


def test_volume_scales_the_samples(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.1, value=10000)

    backend.play(str(path), sinks=["sink-a"], volume=50.0)
    assert wait_for_idle(backend)

    peak = int(np.abs(as_samples(fake_streams[0])).max())
    assert 4500 <= peak <= 5500


def test_fade_in_ramps_from_silence(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.4, value=10000)

    backend.play(str(path), sinks=["sink-a"], fade_in=0.4)
    assert wait_for_idle(backend)

    played = as_samples(fake_streams[0])
    assert abs(int(played[0][0])) < 500
    assert int(played[len(played) // 2][0]) > 3000
    assert int(played[-1][0]) > 8000


def test_one_shot_fade_out_ends_in_silence(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.4, value=10000)

    backend.play(str(path), sinks=["sink-a"], fade_out=0.2)
    assert wait_for_idle(backend)

    played = as_samples(fake_streams[0])
    assert int(played[0][0]) > 9000
    assert abs(int(played[-1][0])) < 500


def test_looping_repeats_until_stopped(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    frames = write_tone(path, seconds=0.05)

    handle = backend.play(str(path), sinks=["sink-a"], loops=-1)
    time.sleep(0.3)
    assert backend.playbacks, "an endless loop should still be running"

    backend.stop(handle)
    assert wait_for_idle(backend)
    assert len(as_samples(fake_streams[0])) > frames


def test_stop_with_fade_out_keeps_playing_briefly(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05, value=10000)

    handle = backend.play(str(path), sinks=["sink-a"], loops=-1)
    backend.stop(handle, fade_out=0.2)
    assert wait_for_idle(backend)

    played = as_samples(fake_streams[0])
    assert abs(int(played[-1][0])) < 1500


def test_stopping_an_unknown_handle_is_harmless(backend):
    backend.stop("playback-does-not-exist")


def test_stream_slots_are_released(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    for _ in range(5):
        backend.play(str(path), sinks=["sink-a", "sink-b"])
        assert wait_for_idle(backend)

    # Leaked slots would eventually make _open_stream refuse to start anything
    assert backend.stream_slots.acquire(blocking=False) is True
    backend.stream_slots.release()


def test_sink_list_is_cached_briefly(backend, monkeypatch):
    calls = []

    def _query():
        calls.append(1)
        return [{"name": "sink-a", "label": "Sink A", "is_default": True}]

    monkeypatch.setattr(backend, "_query_sinks", _query)

    assert backend.list_sinks()[0]["name"] == "sink-a"
    backend.list_sinks()
    backend.list_sinks()
    assert len(calls) == 1


def test_sink_cache_expires(backend, backend_module, monkeypatch):
    monkeypatch.setattr(backend, "_query_sinks", lambda: [{"name": "s", "label": "S", "is_default": True}])
    backend.list_sinks()

    backend.sink_cache_time -= backend_module.SINK_CACHE_SECONDS + 1
    calls = []
    monkeypatch.setattr(backend, "_query_sinks", lambda: calls.append(1) or [])
    backend.list_sinks()

    assert len(calls) == 1


def test_an_empty_sink_query_is_not_cached(backend, monkeypatch):
    calls = []
    monkeypatch.setattr(backend, "_query_sinks", lambda: calls.append(1) or [])

    # Caching an empty result would hide speakers until the TTL expired
    backend.list_sinks()
    backend.list_sinks()
    assert len(calls) == 2


def test_channel_weights_defaults_to_unity(backend_module):
    weights = backend_module.channel_weights(None, 2)
    assert list(weights) == [1.0, 1.0]


def test_channel_weights_passes_a_matching_pair(backend_module):
    assert list(backend_module.channel_weights([1.0, 0.25], 2)) == [1.0, 0.25]


def test_channel_weights_collapses_for_mono(backend_module):
    # A mono file has no sides, so panning must not silence it
    assert list(backend_module.channel_weights([1.0, 0.0], 1)) == [0.5]


def test_channel_weights_repeats_across_more_channels(backend_module):
    assert list(backend_module.channel_weights([1.0, 0.5], 4)) == [1.0, 0.5, 1.0, 0.5]


def test_spatial_gains_are_applied_per_channel(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.1, value=10000)

    backend.play(str(path), sinks=["sink-a"], gains=[[1.0, 0.0]])
    assert wait_for_idle(backend)

    played = as_samples(fake_streams[0])
    assert int(np.abs(played[:, 0]).max()) > 9000   # left kept
    assert int(np.abs(played[:, 1]).max()) == 0     # right muted


def test_each_sink_gets_its_own_gain(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.1, value=10000)

    backend.play(str(path), sinks=["near", "far"], gains=[[1.0, 1.0], [0.25, 0.25]])
    assert wait_for_idle(backend)

    peaks = {s.sink: int(np.abs(as_samples(s)).max()) for s in fake_streams}
    assert peaks["near"] > 9000
    assert 2000 < peaks["far"] < 3000


def test_missing_gain_entries_fall_back_to_unity(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.1, value=10000)

    backend.play(str(path), sinks=["a", "b"], gains=[[0.5, 0.5]])
    assert wait_for_idle(backend)

    peaks = {s.sink: int(np.abs(as_samples(s)).max()) for s in fake_streams}
    assert peaks["b"] > 9000


def test_a_delay_pads_the_stream_with_silence(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    frames = write_tone(path, seconds=0.1, value=9000)

    backend.play(str(path), sinks=["late"], delays=[0.02])
    assert wait_for_idle(backend)

    played = as_samples(fake_streams[0])
    pad = int(0.02 * RATE)
    assert len(played) == pad + frames
    assert int(np.abs(played[:pad]).max()) == 0      # silence first
    assert int(np.abs(played[pad:]).max()) > 8000    # then the sound


def test_each_sink_can_wait_a_different_amount(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    frames = write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["first", "second"], delays=[0.0, 0.01])
    assert wait_for_idle(backend)

    lengths = {s.sink: len(as_samples(s)) for s in fake_streams}
    assert lengths["first"] == frames
    assert lengths["second"] == frames + int(0.01 * RATE)


def test_no_delay_means_no_padding(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    frames = write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"])
    assert wait_for_idle(backend)
    assert len(as_samples(fake_streams[0])) == frames


def test_sink_kind_trusts_the_form_factor(backend_module):
    assert backend_module.sink_kind({"device.form_factor": "headset"}) == "headset"
    assert backend_module.sink_kind({"device.form_factor": "headphone"}) == "headset"
    assert backend_module.sink_kind({"device.form_factor": "speaker"}) == "speaker"
    assert backend_module.sink_kind({"device.form_factor": "internal"}) == "speaker"


def test_sink_kind_falls_back_to_the_active_port(backend_module):
    # An internal card exposes headphones as a port, not as its own sink
    props = {"device.icon_name": "audio-card-analog-pci"}
    assert backend_module.sink_kind(props, "analog-output-headphones") == "headset"
    assert backend_module.sink_kind(props, "analog-output-speaker") == "speaker"


def test_sink_kind_falls_back_to_the_icon(backend_module):
    assert backend_module.sink_kind({"device.icon_name": "audio-headphones"}) == "headset"
    assert backend_module.sink_kind({"device.icon_name": "audio-speakers"}) == "speaker"


def test_sink_kind_defaults_to_speaker(backend_module):
    # The analog card on this machine reports no form factor at all
    assert backend_module.sink_kind({}) == "speaker"
    assert backend_module.sink_kind({"device.form_factor": None}, "") == "speaker"


def write_mono(path, seconds=0.1, value=9000):
    frames = int(RATE * seconds)
    sf.write(str(path), np.full((frames, 1), value, dtype=np.int16), RATE, subtype="PCM_16")
    return frames


def test_mono_is_upmixed_so_spatial_can_pan_it(backend, tmp_path, fake_streams):
    path = tmp_path / "mono.wav"
    frames = write_mono(path)

    backend.play(str(path), sinks=["ears"], gains=[[1.0, 0.0]])
    assert wait_for_idle(backend)

    played = np.frombuffer(bytes(fake_streams[0].payload), dtype=np.int16).reshape(-1, 2)
    assert len(played) == frames
    assert int(np.abs(played[:, 0]).max()) > 8000   # left keeps the sound
    assert int(np.abs(played[:, 1]).max()) == 0     # right is panned away


def test_mono_stays_mono_without_spatial(backend, tmp_path, fake_streams):
    path = tmp_path / "mono.wav"
    frames = write_mono(path)

    backend.play(str(path), sinks=["a"])
    assert wait_for_idle(backend)

    # No spatial gains, so nothing is upmixed and the stream stays single channel
    played = np.frombuffer(bytes(fake_streams[0].payload), dtype=np.int16)
    assert len(played) == frames


def test_stereo_is_untouched_by_the_upmix_path(backend, tmp_path, fake_streams):
    path = tmp_path / "stereo.wav"
    frames = write_tone(path, seconds=0.1)

    backend.play(str(path), sinks=["a"], gains=[[1.0, 1.0]])
    assert wait_for_idle(backend)
    assert len(as_samples(fake_streams[0])) == frames


def test_bluetooth_detection(backend_module):
    assert backend_module.is_bluetooth({"device.bus": "bluetooth"}) is True
    assert backend_module.is_bluetooth({"device.bus": "Bluetooth"}) is True
    assert backend_module.is_bluetooth({"device.bus": "pci"}) is False
    # bluez names the sink after the adapter, which covers a missing bus property
    assert backend_module.is_bluetooth({}, "bluez_output.AC_12_2F.1") is True
    assert backend_module.is_bluetooth({}, "alsa_output.pci-0000") is False


def test_a_sound_that_ends_naturally_plays_its_tail_out(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"])
    assert wait_for_idle(backend)

    assert fake_streams[0].drained is True
    assert fake_streams[0].flushed is False


def test_stopping_discards_whatever_is_still_queued(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    handle = backend.play(str(path), sinks=["a"], loops=-1)
    backend.stop(handle)
    assert wait_for_idle(backend)

    # Draining here would keep playing the server's buffer, making a stop audibly late
    assert fake_streams[0].flushed is True
    assert fake_streams[0].drained is False


def test_rate_scale_shifts_the_stream_rate(backend, tmp_path, monkeypatch):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)
    opened = []

    def _open(sink, rate, channels):
        opened.append(rate)
        return FakeStream()

    monkeypatch.setattr(backend, "_open_stream", _open)

    backend.play(str(path), sinks=["a"], rate_scale=1.1)
    assert wait_for_idle(backend)
    assert opened == [int(RATE * 1.1)]


def test_rate_scale_defaults_to_the_file_rate(backend, tmp_path, monkeypatch):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)
    opened = []
    monkeypatch.setattr(backend, "_open_stream", lambda sink, rate, channels: opened.append(rate) or FakeStream())

    backend.play(str(path), sinks=["a"])
    assert wait_for_idle(backend)
    assert opened == [RATE]


def test_an_absurd_rate_scale_is_clamped(backend, tmp_path, monkeypatch):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)
    opened = []
    monkeypatch.setattr(backend, "_open_stream", lambda sink, rate, channels: opened.append(rate) or FakeStream())

    backend.play(str(path), sinks=["a"], rate_scale=0.0)
    assert wait_for_idle(backend)
    assert opened[0] >= 1000


def test_stop_all_stops_every_playback(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"], loops=-1)
    backend.play(str(path), sinks=["b"], loops=-1)
    assert len(backend.playbacks) == 2

    assert backend.stop_all() == 2
    assert wait_for_idle(backend)
    assert all(stream.flushed for stream in fake_streams)


def test_stop_all_with_nothing_playing(backend):
    assert backend.stop_all() == 0


def test_sink_kinds_match_the_frontend_enum(backend_module):
    """The backend cannot import the frontend, so the two spellings of these values must be checked."""
    from actions.audio_targets import SinkKind

    assert backend_module.HEADSET == SinkKind.HEADSET.value
    assert backend_module.SPEAKER == SinkKind.SPEAKER.value
    assert {backend_module.HEADSET, backend_module.SPEAKER} == {kind.value for kind in SinkKind}


def test_a_tagged_loop_reports_itself_as_playing(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    assert backend.is_playing("bed") is False
    backend.play(str(path), sinks=["a"], loops=-1, tag="bed")
    assert backend.is_playing("bed") is True

    backend.stop_tag("bed")
    assert wait_for_idle(backend)
    assert backend.is_playing("bed") is False


def test_stopping_a_tag_leaves_other_tags_alone(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"], loops=-1, tag="rain")
    backend.play(str(path), sinks=["b"], loops=-1, tag="klaxon")

    assert backend.stop_tag("klaxon") == 1
    assert backend.is_playing("rain") is True

    backend.stop_tag("rain")
    assert wait_for_idle(backend)


def test_an_untagged_sound_is_never_matched(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"], loops=-1)
    assert backend.is_playing("") is False
    assert backend.stop_tag("") == 0

    backend.stop_all()
    assert wait_for_idle(backend)


def test_a_stopping_loop_no_longer_counts_as_playing(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"], loops=-1, tag="bed")
    backend.stop_tag("bed", fade_out=5.0)

    # Marked stopping, so a second press starts a new loop rather than toggling nothing
    assert backend.is_playing("bed") is False
    backend.stop_all()
    assert wait_for_idle(backend)


def test_unknown_tags_are_harmless(backend):
    assert backend.stop_tag("nothing-here") == 0
    assert backend.is_playing("nothing-here") is False


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_playback_state_reports_the_three_states(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    assert backend.playback_state("bed") == "stopped"

    backend.play(str(path), sinks=["a"], loops=-1, tag="bed")
    assert backend.playback_state("bed") == "playing"

    backend.pause_tag("bed")
    assert wait_until(lambda: backend.playback_state("bed") == "paused")

    backend.pause_tag("bed", False)
    assert backend.playback_state("bed") == "playing"

    backend.stop_tag("bed")
    assert wait_for_idle(backend)
    assert backend.playback_state("bed") == "stopped"


def test_pausing_stops_the_writer_and_resuming_continues(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"], loops=-1, tag="bed")
    stream = fake_streams[0]

    assert wait_until(lambda: len(stream.payload) > 0)
    backend.pause_tag("bed")
    time.sleep(0.15)
    frozen = len(stream.payload)

    # Nothing more is written while paused
    time.sleep(0.15)
    assert len(stream.payload) == frozen

    backend.pause_tag("bed", False)
    assert wait_until(lambda: len(stream.payload) > frozen)

    backend.stop_tag("bed")
    assert wait_for_idle(backend)


def test_a_paused_playback_can_still_be_stopped(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"], loops=-1, tag="bed")
    backend.pause_tag("bed")
    assert wait_until(lambda: backend.playback_state("bed") == "paused")

    # A paused writer must notice the stop, or the thread and its stream slot leak
    backend.stop_tag("bed")
    assert wait_for_idle(backend)


def test_stop_all_releases_paused_playbacks(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"], loops=-1, tag="one")
    backend.play(str(path), sinks=["b"], loops=-1, tag="two")
    backend.pause_tag("one")
    assert wait_until(lambda: backend.playback_state("one") == "paused")

    backend.stop_all()
    assert wait_for_idle(backend)


def test_pausing_one_tag_leaves_another_playing(backend, tmp_path, fake_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"], loops=-1, tag="rain")
    backend.play(str(path), sinks=["b"], loops=-1, tag="klaxon")

    assert backend.pause_tag("rain") == 1
    assert wait_until(lambda: backend.playback_state("rain") == "paused")
    assert backend.playback_state("klaxon") == "playing"

    backend.stop_all()
    assert wait_for_idle(backend)


def test_pausing_an_unknown_tag_is_harmless(backend):
    assert backend.pause_tag("nothing") == 0
    assert backend.playback_state("nothing") == "stopped"
    assert backend.pause_tag("") == 0


@pytest.fixture
def held_streams(backend, monkeypatch):
    """Blocks the writers inside write(), so a one-shot stays alive long enough to be counted."""
    release = threading.Event()
    created = []

    class HeldStream(FakeStream):
        def write(self, data):
            release.wait(timeout=5)
            super().write(data)

    def _open(sink, rate, channels):
        stream = HeldStream()
        stream.sink = sink
        created.append(stream)
        return stream

    monkeypatch.setattr(backend, "_open_stream", _open)
    yield release

    release.set()


def test_one_tag_stops_every_sound_an_action_started(backend, tmp_path, held_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    # An action tags its one-shots too, so a burst of presses stays one thing to stop
    for _ in range(3):
        backend.play(str(path), sinks=["a"], tag="key-1x1")
    backend.play(str(path), sinks=["a"], tag="key-2x2")

    assert wait_until(lambda: len(backend.playbacks) == 4)
    assert backend.stop_tag("key-1x1") == 3
    assert backend.playback_state("key-2x2") == "playing"

    held_streams.set()
    assert wait_until(lambda: backend.playback_state("key-1x1") == "stopped")

    backend.stop_all()
    assert wait_for_idle(backend)


def test_a_removed_action_takes_its_loop_and_its_one_shot_with_it(backend, tmp_path, held_streams):
    path = tmp_path / "tone.wav"
    write_tone(path, seconds=0.05)

    backend.play(str(path), sinks=["a"], loops=-1, tag="gone")
    backend.play(str(path), sinks=["b"], tag="gone")

    assert wait_until(lambda: len(backend.playbacks) == 2)
    assert backend.stop_tag("gone") == 2

    held_streams.set()
    assert wait_for_idle(backend)
