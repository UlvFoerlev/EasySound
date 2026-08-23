import math

import pytest

from actions.spatial import (
    DEFAULT_ROOM_SIZE,
    MAX_ROOM_SIZE,
    MIN_ROOM_SIZE,
    channel_gains,
    clamp_position,
    clamp_room_size,
    clamp_unit,
    dbap_gains,
    default_layout,
    normalize_positions,
    stereo_balance,
)

FRONT = (0.0, 0.8)
BACK = (0.0, -0.8)
LEFT = (-0.8, 0.0)
RIGHT = (0.8, 0.0)


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.5, 0.5),
        (9, 1.0),
        (-9, -1.0),
        ("nope", 0.0),
        (None, 0.0),
        (float("nan"), 0.0),
    ],
)
def test_clamp_unit_bounds_and_rejects_junk(value, expected):
    assert clamp_unit(value) == expected


@pytest.mark.parametrize(
    "position,expected",
    [
        ([0.2, -0.4], (0.2, -0.4)),
        ((5, -5), (1.0, -1.0)),
        (None, (0.0, 0.0)),
        ([1], (0.0, 0.0)),
        ("x", (0.0, 0.0)),
    ],
)
def test_clamp_position_shapes(position, expected):
    assert clamp_position(position) == expected


def test_normalize_positions_drops_malformed():
    raw = {"a": [0.1, 0.2], "b": "junk", "": [0, 0], 5: [0, 0]}
    assert normalize_positions(raw) == {"a": (0.1, 0.2), "b": (0.0, 0.0)}


def test_normalize_positions_handles_non_dict():
    assert normalize_positions(None) == {}
    assert normalize_positions([]) == {}


def test_default_layout_puts_the_first_speaker_in_front():
    layout = default_layout(["a", "b", "c", "d"])
    assert layout["a"] == (0.0, 0.8)
    # evenly spaced: four speakers land front, right, back, left
    assert layout["b"][0] > 0.7 and abs(layout["b"][1]) < 0.001
    assert layout["c"][1] < -0.7
    assert layout["d"][0] < -0.7


def test_default_layout_edge_cases():
    assert default_layout([]) == {}
    assert default_layout(["only"]) == {"only": (0.0, 0.8)}


def test_gain_is_highest_for_the_nearest_speaker():
    positions = {"front": FRONT, "back": BACK}
    gains = dbap_gains(FRONT, positions)
    assert gains["front"] > gains["back"]


def test_a_source_behind_favours_the_rear_speakers():
    positions = {"front": FRONT, "back": BACK}
    gains = dbap_gains(BACK, positions)
    assert gains["back"] > gains["front"]


def test_equidistant_speakers_share_the_sound():
    positions = {"left": LEFT, "right": RIGHT}
    gains = dbap_gains((0.0, 0.0), positions)
    assert math.isclose(gains["left"], gains["right"])


@pytest.mark.parametrize(
    "source", [FRONT, BACK, LEFT, RIGHT, (0.0, 0.0), (0.5, -0.3)]
)
def test_power_is_constant_wherever_the_source_sits(source):
    positions = {"a": FRONT, "b": BACK, "c": LEFT, "d": RIGHT}
    power = sum(gain * gain for gain in dbap_gains(source, positions).values())

    assert math.isclose(power, 1.0, abs_tol=1e-6)


@pytest.mark.parametrize("source", [FRONT, BACK, LEFT, (1.0, 1.0), (-1.0, -1.0)])
def test_no_gain_exceeds_unity(source):
    positions = {"a": FRONT, "b": BACK, "c": LEFT}

    assert all(0.0 <= g <= 1.0 for g in dbap_gains(source, positions).values())


def test_a_single_speaker_plays_at_full_gain():
    assert dbap_gains(LEFT, {"only": RIGHT}) == {"only": 1.0}


def test_dbap_with_no_speakers():
    assert dbap_gains(FRONT, {}) == {}


def test_stereo_balance_centre_is_unity():
    assert stereo_balance(0.0) == (1.0, 1.0)


def test_stereo_balance_pans_without_boosting():
    assert stereo_balance(-1.0) == (1.0, 0.0)
    assert stereo_balance(1.0) == (0.0, 1.0)
    left, right = stereo_balance(-0.5)
    assert left == 1.0 and right == 0.5


def test_two_speakers_pan_by_placement_not_within_each_speaker():
    positions = {"left": LEFT, "right": RIGHT}
    gains = channel_gains([-0.8, 0.0], ["left", "right"], positions)

    assert gains["left"][0] > gains["right"][0]
    # A real speaker's drivers do not move, so with geometry available its channels stay level
    assert gains["left"][0] == gains["left"][1]
    assert gains["right"][0] == gains["right"][1]


def test_channel_gains_for_one_headset_keeps_direction():
    # A single stereo output cannot use placement, so balance carries the whole effect
    gains = channel_gains([-1.0, 0.0], ["headset"], {"headset": (0.0, 0.0)})
    assert gains["headset"] == (1.0, 0.0)


def test_channel_gains_centre_is_untouched():
    gains = channel_gains([0.0, 0.0], ["only"], {"only": (0.0, 0.5)})
    assert gains["only"] == (1.0, 1.0)


def test_channel_gains_tolerates_missing_positions():
    gains = channel_gains([0.0, 0.0], ["a", "b"], {})
    assert set(gains) == {"a", "b"}
    assert all(0.0 <= g <= 1.0 for pair in gains.values() for g in pair)


def test_channel_gains_ignores_unknown_sinks_in_positions():
    gains = channel_gains([0.0, 0.0], ["a"], {"a": FRONT, "ghost": BACK})
    assert set(gains) == {"a"}


@pytest.mark.parametrize(
    "value,expected",
    [
        (6.0, 6.0),
        (0.1, MIN_ROOM_SIZE),
        (500, MAX_ROOM_SIZE),
        ("nope", DEFAULT_ROOM_SIZE),
        (None, DEFAULT_ROOM_SIZE),
        (float("nan"), DEFAULT_ROOM_SIZE),
    ],
)
def test_room_size_is_clamped_and_defaults_safely(value, expected):
    assert clamp_room_size(value) == expected


def test_the_map_spans_the_full_room_width():
    from actions.spatial import distance_metres

    # a 4 m room: the edge of the map is 2 m from the listener at the centre
    assert distance_metres((0.0, 0.0), (0.0, 1.0), 4.0) == 2.0
    assert distance_metres((0.0, 0.0), (0.0, 0.5), 4.0) == 1.0


def test_listener_distances_for_the_arrows():
    from actions.spatial import listener_distances

    distances = listener_distances({"front": (0.0, 1.0), "near": (0.0, 0.25)}, 8.0)
    assert distances == {"front": 4.0, "near": 1.0}


def test_the_speaker_nearest_the_source_fires_first():
    from actions.spatial import source_delays

    delays = source_delays(BACK, {"front": FRONT, "back": BACK}, 4.0)
    assert delays["back"] == 0.0
    assert delays["front"] > 0.0


def test_delay_matches_the_speed_of_sound():
    from actions.spatial import SPEED_OF_SOUND, source_delays

    # a 10 m room: the source sits on the front speaker, so the back one is 10 m further away
    delays = source_delays((0.0, 1.0), {"front": (0.0, 1.0), "back": (0.0, -1.0)}, 10.0)
    assert delays["front"] == 0.0
    assert math.isclose(delays["back"], 10.0 / SPEED_OF_SOUND, abs_tol=0.0005)


def test_a_single_speaker_never_waits():
    from actions.spatial import source_delays

    # With nothing to be early or late against, a lone speaker is its own reference
    assert source_delays((0.0, 1.0), {"only": (0.0, -1.0)}, 30.0) == {"only": 0.0}


def test_delay_is_capped():
    from actions.spatial import MAX_DELAY_SECONDS, source_delays

    # 30 m apart is 87 ms of flight time, which is an echo rather than a spatial cue
    delays = source_delays(
        (0.0, 1.0), {"near": (0.0, 1.0), "far": (0.0, -1.0)}, 30.0
    )
    assert delays["far"] == MAX_DELAY_SECONDS


def test_equidistant_speakers_share_a_delay():
    from actions.spatial import source_delays

    delays = source_delays((0.0, 0.0), {"left": LEFT, "right": RIGHT}, 5.0)
    assert delays["left"] == delays["right"] == 0.0


def test_source_delays_with_no_speakers():
    from actions.spatial import source_delays

    assert source_delays(FRONT, {}, 4.0) == {}


def test_every_requested_sink_gets_a_gain():
    gains = channel_gains(FRONT, ["a", "ears"], {"a": FRONT}, headsets={"ears"})
    assert set(gains) == {"a", "ears"}


def test_one_device_keeps_its_level_when_spatial_is_enabled():
    # Toggling spatial must not make a lone device quieter, so a single-device pool is max-normalised
    assert max(channel_gains((0.0, 0.0), ["hs"], {}, headsets={"hs"})["hs"]) == 1.0
    assert max(channel_gains((-0.7, 0.2), ["hs"], {}, headsets={"hs"})["hs"]) == 1.0


def test_emitter_ids_and_defaults():
    from actions.spatial import (
        EAR_SEPARATION,
        Side,
        default_emitter_position,
        emitter_id,
        emitters_for,
    )

    assert emitter_id("sink") == "sink"
    # Both forms: the enum in code, a plain string when parsed back out of settings
    assert emitter_id("sink", Side.LEFT) == "sink#left"
    assert emitter_id("sink", "left") == "sink#left"
    assert emitters_for("spk", is_headset=False) == ["spk"]
    assert emitters_for("hs", is_headset=True) == ["hs#left", "hs#right"]

    assert default_emitter_position("hs#left") == (-EAR_SEPARATION, 0.0)
    assert default_emitter_position("hs#right") == (EAR_SEPARATION, 0.0)
    assert default_emitter_position("spk") == (0.0, 0.0)


def test_emitter_layout_splits_only_headsets():
    from actions.spatial import emitter_layout

    layout = emitter_layout(["spk", "hs"], headsets={"hs"}, positions={"spk": FRONT})
    assert set(layout) == {"spk", "hs#left", "hs#right"}
    assert layout["spk"] == FRONT


def test_a_headset_pans_left_and_right_by_geometry():
    gains = channel_gains(LEFT, ["hs"], {}, headsets={"hs"})
    left, right = gains["hs"]
    assert left > right


def test_a_headset_is_centred_when_the_sound_is_centred():
    left, right = channel_gains((0.0, 0.0), ["hs"], {}, headsets={"hs"})["hs"]
    assert math.isclose(left, right)


def test_a_headset_cannot_tell_front_from_back():
    # Honest limitation: with equal ear distances, amplitude alone carries no front/back cue
    front = channel_gains((0.0, 0.9), ["hs"], {}, headsets={"hs"})["hs"]
    back = channel_gains((0.0, -0.9), ["hs"], {}, headsets={"hs"})["hs"]
    assert front == back


def test_earpieces_can_be_placed_individually():
    positions = {"hs#left": (-0.9, 0.0), "hs#right": (0.9, 0.0)}
    wide = channel_gains((-0.9, 0.0), ["hs"], positions, headsets={"hs"})["hs"]
    narrow = channel_gains((-0.9, 0.0), ["hs"], {}, headsets={"hs"})["hs"]

    # Ears further apart give a stronger separation for the same source
    assert wide[0] - wide[1] > narrow[0] - narrow[1]


def test_a_headset_and_speakers_share_one_pool():
    positions = {"spk": FRONT}
    gains = channel_gains(FRONT, ["spk", "hs"], positions, headsets={"hs"})

    # The speaker sits on the source, so it should dominate both ears of the headset
    assert gains["spk"][0] > max(gains["hs"])


def test_a_lone_speaker_still_gets_a_balance_cue():
    left, right = channel_gains((-1.0, 0.0), ["spk"], {"spk": FRONT})["spk"]
    assert left > right


def test_merging_positions_keeps_speakers_the_dialog_never_saw():
    from actions.spatial import merge_positions

    stored = {"a": [0.5, 0.5], "b": [-0.5, -0.5], "hs#left": [-0.3, 0.0]}
    # A dialog opened on one speaker must not wipe the rest of the room
    merged = merge_positions(stored, {"a": (0.1, 0.2)})

    assert merged == {"a": (0.1, 0.2), "b": (-0.5, -0.5), "hs#left": (-0.3, 0.0)}


def test_merging_clamps_and_survives_junk():
    from actions.spatial import merge_positions

    assert merge_positions(None, {"a": (9, -9)}) == {"a": (1.0, -1.0)}
    assert merge_positions({"a": "junk"}, {}) == {"a": (0.0, 0.0)}
    assert merge_positions({"a": [0.2, 0.2]}, None) == {"a": (0.2, 0.2)}
