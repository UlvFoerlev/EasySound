import math

from actions.spatial import (
    channel_gains,
    clamp_position,
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


def test_clamp_unit_bounds_and_rejects_junk():
    assert clamp_unit(0.5) == 0.5
    assert clamp_unit(9) == 1.0
    assert clamp_unit(-9) == -1.0
    assert clamp_unit("nope") == 0.0
    assert clamp_unit(None) == 0.0
    assert clamp_unit(float("nan")) == 0.0


def test_clamp_position_shapes():
    assert clamp_position([0.2, -0.4]) == (0.2, -0.4)
    assert clamp_position((5, -5)) == (1.0, -1.0)
    assert clamp_position(None) == (0.0, 0.0)
    assert clamp_position([1]) == (0.0, 0.0)
    assert clamp_position("x") == (0.0, 0.0)


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


def test_power_is_constant_wherever_the_source_sits():
    positions = {"a": FRONT, "b": BACK, "c": LEFT, "d": RIGHT}
    for source in (FRONT, BACK, LEFT, RIGHT, (0.0, 0.0), (0.5, -0.3)):
        power = sum(gain * gain for gain in dbap_gains(source, positions).values())
        assert math.isclose(power, 1.0, abs_tol=1e-6)


def test_no_gain_exceeds_unity():
    positions = {"a": FRONT, "b": BACK, "c": LEFT}
    for source in (FRONT, BACK, LEFT, (1.0, 1.0), (-1.0, -1.0)):
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


def test_channel_gains_combine_placement_and_balance():
    positions = {"left": LEFT, "right": RIGHT}
    gains = channel_gains([-0.8, 0.0], ["left", "right"], positions)

    # source to the left: the left speaker is loudest, and every right channel is attenuated
    assert gains["left"][0] > gains["right"][0]
    assert gains["left"][1] < gains["left"][0]
    assert gains["right"][1] < gains["right"][0]

    # only a fully lateral source mutes the opposite channel
    assert channel_gains([-1.0, 0.0], ["left"], {"left": LEFT})["left"][1] == 0.0


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
