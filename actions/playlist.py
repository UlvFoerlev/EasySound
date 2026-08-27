import random
from enum import Enum
from typing import Any


class Order(str, Enum):
    RANDOM = "random"
    SEQUENCE = "sequence"
    SHUFFLE = "shuffle"


ORDER_LOCALES = {
    Order.RANDOM: "action.play-sound.order.random",
    Order.SEQUENCE: "action.play-sound.order.sequence",
    Order.SHUFFLE: "action.play-sound.order.shuffle",
}

MAX_RATE_VARIATION = 50.0


def normalize_paths(primary: Any, extra: Any) -> list[str]:
    """The pool is the main sound plus any extras, in order, ignoring blanks and duplicates."""
    candidates = [primary] if isinstance(primary, str) else []
    if isinstance(extra, list):
        candidates += [path for path in extra if isinstance(path, str)]

    pool = []
    for path in candidates:
        cleaned = path.strip()
        if cleaned and cleaned not in pool:
            pool.append(cleaned)

    return pool


def resolve_sounds(sounds: Any, primary: Any, extra: Any) -> list[str]:
    """The sound list, or the pre-list settings when an action has not been edited since."""
    if isinstance(sounds, list):
        return normalize_paths(None, sounds)

    return normalize_paths(primary, extra)


def normalize_order(value: Any) -> Order:
    try:
        return Order(value)
    except ValueError:
        return Order.RANDOM


class Picker:
    """Chooses which sound plays next; the rotation and shuffle state is per action and not persisted."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.cursor = 0
        self.bag: list[str] = []

    def pick(self, pool: list[str], order: Any = Order.RANDOM) -> str | None:
        if not pool:
            return None
        if len(pool) == 1:
            return pool[0]

        order = normalize_order(order)

        if order is Order.SEQUENCE:
            # Wraps on the current pool, so removing a sound cannot leave the cursor out of range
            self.cursor %= len(pool)
            path = pool[self.cursor]
            self.cursor = (self.cursor + 1) % len(pool)

            return path

        if order is Order.SHUFFLE:
            # A bag that refills only once empty, so nothing repeats until everything has played
            self.bag = [path for path in self.bag if path in pool]
            if not self.bag:
                self.bag = list(pool)
                self.rng.shuffle(self.bag)
                if len(self.bag) > 1 and self.bag[0] == getattr(self, "last", None):
                    self.bag.append(self.bag.pop(0))

            path = self.bag.pop(0)
            self.last = path

            return path

        return self.rng.choice(pool)


def clamp_variation(percent: Any) -> float:
    try:
        number = float(percent)
    except (TypeError, ValueError):
        return 0.0

    if number != number:  # NaN
        return 0.0

    return max(0.0, min(MAX_RATE_VARIATION, number))


def rate_scale(percent: Any, rng: random.Random | None = None) -> float:
    """A random speed factor within +/- percent; pitch and tempo move together when resampling."""
    variation = clamp_variation(percent) / 100.0
    if variation <= 0:
        return 1.0

    rng = rng or random
    return round(1.0 + rng.uniform(-variation, variation), 6)
