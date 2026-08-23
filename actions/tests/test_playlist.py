import random

from actions.playlist import (
    MAX_RATE_VARIATION,
    RANDOM,
    SEQUENCE,
    SHUFFLE,
    ORDER_LOCALES,
    ORDERS,
    Picker,
    clamp_variation,
    normalize_order,
    normalize_paths,
    rate_scale,
)

A, B, C = "/s/a.wav", "/s/b.wav", "/s/c.wav"


def test_pool_is_primary_plus_extras():
    assert normalize_paths(A, [B, C]) == [A, B, C]


def test_pool_drops_blanks_and_duplicates():
    assert normalize_paths(A, [A, "", "   ", B, B]) == [A, B]


def test_pool_survives_junk():
    assert normalize_paths(None, None) == []
    assert normalize_paths(A, "not a list") == [A]
    assert normalize_paths(A, [None, 5, B]) == [A, B]


def test_pool_trims_whitespace():
    assert normalize_paths(f"  {A}  ", []) == [A]


def test_order_falls_back_to_random():
    assert normalize_order("nonsense") == RANDOM
    assert normalize_order(None) == RANDOM
    for order in ORDERS:
        assert normalize_order(order) == order


def test_every_order_has_a_locale_key():
    assert set(ORDER_LOCALES) == set(ORDERS)


def test_one_sound_always_plays_regardless_of_order():
    picker = Picker(random.Random(1))
    for order in ORDERS:
        assert picker.pick([A], order) == A


def test_an_empty_pool_plays_nothing():
    assert Picker().pick([], RANDOM) is None


def test_sequence_rotates_and_wraps():
    picker = Picker()
    picks = [picker.pick([A, B, C], SEQUENCE) for _ in range(7)]
    assert picks == [A, B, C, A, B, C, A]


def test_sequence_survives_the_pool_shrinking():
    picker = Picker()
    picker.pick([A, B, C], SEQUENCE)
    picker.pick([A, B, C], SEQUENCE)
    # The third sound is deleted while the cursor points past the new end
    assert picker.pick([A], SEQUENCE) == A


def test_shuffle_plays_everything_before_repeating():
    picker = Picker(random.Random(7))
    pool = [A, B, C]
    first_round = {picker.pick(pool, SHUFFLE) for _ in range(3)}

    assert first_round == set(pool)


def test_shuffle_avoids_an_immediate_repeat_across_rounds():
    picker = Picker(random.Random(3))
    pool = [A, B, C]
    picks = [picker.pick(pool, SHUFFLE) for _ in range(12)]

    assert all(picks[i] != picks[i + 1] for i in range(len(picks) - 1))


def test_shuffle_forgets_removed_sounds():
    picker = Picker(random.Random(5))
    picker.pick([A, B, C], SHUFFLE)
    for _ in range(4):
        assert picker.pick([A, B], SHUFFLE) in (A, B)


def test_random_stays_inside_the_pool():
    picker = Picker(random.Random(2))
    assert all(picker.pick([A, B], RANDOM) in (A, B) for _ in range(20))


def test_variation_is_clamped_and_junk_safe():
    assert clamp_variation(10) == 10.0
    assert clamp_variation(-5) == 0.0
    assert clamp_variation(999) == MAX_RATE_VARIATION
    assert clamp_variation("nope") == 0.0
    assert clamp_variation(None) == 0.0
    assert clamp_variation(float("nan")) == 0.0


def test_no_variation_means_untouched_playback():
    assert rate_scale(0) == 1.0
    assert rate_scale(None) == 1.0


def test_variation_stays_within_the_requested_range():
    rng = random.Random(11)
    for _ in range(50):
        scale = rate_scale(10, rng)
        assert 0.9 <= scale <= 1.1


def test_variation_actually_varies():
    rng = random.Random(4)
    assert len({rate_scale(20, rng) for _ in range(20)}) > 1


def test_resolved_sounds_prefer_the_list():
    from actions.playlist import resolve_sounds

    assert resolve_sounds([B, C], A, []) == [B, C]


def test_resolved_sounds_fall_back_to_the_pre_list_settings():
    from actions.playlist import resolve_sounds

    # An action saved before the list existed keeps its sound in filepath plus extras
    assert resolve_sounds(None, A, [B]) == [A, B]
    assert resolve_sounds(None, A, None) == [A]


def test_an_empty_list_is_respected_not_treated_as_missing():
    from actions.playlist import resolve_sounds

    # Deleting every sound must not resurrect the old filepath
    assert resolve_sounds([], A, [B]) == []


def test_resolved_sounds_clean_their_input():
    from actions.playlist import resolve_sounds

    assert resolve_sounds([A, A, "", None, f"  {B}  "], None, None) == [A, B]
