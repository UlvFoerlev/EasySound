import math
from enum import Enum
from typing import Any

# Distance added before the rolloff, so a source sitting on a speaker cannot produce an infinite gain
BLUR = 0.25
ROLLOFF = 2.0

SPEED_OF_SOUND = 343.0
DEFAULT_ROOM_SIZE = 4.0
MIN_ROOM_SIZE = 1.0
MAX_ROOM_SIZE = 30.0
# Beyond this a "delay" is just a late echo, so it is clamped rather than trusted
MAX_DELAY_SECONDS = 0.05


def clamp_room_size(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return DEFAULT_ROOM_SIZE

    if math.isnan(number):
        return DEFAULT_ROOM_SIZE

    return max(MIN_ROOM_SIZE, min(MAX_ROOM_SIZE, number))


def unit_to_metres(room_size: Any) -> float:
    """The map spans the room's full width, so one unit of map is half the room."""
    return clamp_room_size(room_size) / 2.0


def distance_metres(
    point_a: tuple[float, float],
    point_b: tuple[float, float],
    room_size: Any = DEFAULT_ROOM_SIZE,
) -> float:
    scale = unit_to_metres(room_size)

    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1]) * scale


def listener_distances(
    positions: dict[str, tuple[float, float]],
    room_size: Any = DEFAULT_ROOM_SIZE,
) -> dict[str, float]:
    """Metres from the listener to each speaker, for the arrows drawn on the map."""
    return {
        sink: round(distance_metres((0.0, 0.0), point, room_size), 2)
        for sink, point in positions.items()
    }


def source_delays(
    source: Any,
    positions: dict[str, tuple[float, float]],
    room_size: Any = DEFAULT_ROOM_SIZE,
) -> dict[str, float]:
    """Seconds each speaker waits so the wavefronts superpose as if they left the source."""
    if not positions:
        return {}

    point = clamp_position(source)
    distances = {
        sink: distance_metres(point, speaker, room_size)
        for sink, speaker in positions.items()
    }
    earliest = min(distances.values())

    return {
        sink: round(
            min((distance - earliest) / SPEED_OF_SOUND, MAX_DELAY_SECONDS), 6
        )
        for sink, distance in distances.items()
    }


def clamp_unit(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0

    if math.isnan(number):
        return 0.0

    return max(-1.0, min(1.0, number))


def clamp_position(position: Any) -> tuple[float, float]:
    """Positions are listener-relative: (0, 0) is the listener, -1..1 spans the room in each axis."""
    if isinstance(position, (list, tuple)) and len(position) == 2:
        return clamp_unit(position[0]), clamp_unit(position[1])

    return 0.0, 0.0


def normalize_positions(raw: Any) -> dict[str, tuple[float, float]]:
    # Saved settings are user-editable json, so anything malformed is dropped rather than raising
    if not isinstance(raw, dict):
        return {}

    positions = {}
    for name, position in raw.items():
        if isinstance(name, str) and name:
            positions[name] = clamp_position(position)

    return positions


def default_layout(sinks: list[str]) -> dict[str, tuple[float, float]]:
    """Speakers with no saved position start evenly spaced on a ring, first one in front."""
    count = len(sinks)
    if count == 0:
        return {}

    radius = 0.8
    layout = {}
    for index, sink in enumerate(sinks):
        angle = math.tau * index / count
        layout[sink] = (
            round(radius * math.sin(angle), 4),
            round(radius * math.cos(angle), 4),
        )

    return layout


def dbap_gains(
    source: tuple[float, float],
    positions: dict[str, tuple[float, float]],
    blur: float = BLUR,
    rolloff: float = ROLLOFF,
) -> dict[str, float]:
    """Per-speaker gain by distance-based amplitude panning, normalised to constant power."""
    if not positions:
        return {}

    weights = {}
    for sink, position in positions.items():
        dx = source[0] - position[0]
        dy = source[1] - position[1]
        distance = math.sqrt(dx * dx + dy * dy + blur * blur)
        weights[sink] = 1.0 / (distance**rolloff)

    power = math.sqrt(sum(weight * weight for weight in weights.values()))
    if power <= 0:
        return {sink: 0.0 for sink in positions}

    return {sink: round(weight / power, 6) for sink, weight in weights.items()}


def stereo_balance(source_x: float) -> tuple[float, float]:
    """Left/right weights for one stereo output; attenuates the far side so the centre stays at unity."""
    x = clamp_unit(source_x)

    return (1.0 if x <= 0 else round(1.0 - x, 6), 1.0 if x >= 0 else round(1.0 + x, 6))


class Side(str, Enum):
    LEFT = "left"
    RIGHT = "right"


EAR_SEPARATION = 0.3


def emitter_id(sink: str, side: "Side | str | None" = None) -> str:
    """A speaker is one emitter; a headset is two, one per ear, each placed on its own."""
    if side is None:
        return sink

    # Accepts a plain string too, since emitter ids are parsed back out of saved settings
    return f"{sink}#{getattr(side, 'value', side)}"


def emitters_for(sink: str, is_headset: bool) -> list[str]:
    if is_headset:
        return [emitter_id(sink, Side.LEFT), emitter_id(sink, Side.RIGHT)]

    return [emitter_id(sink)]


def default_emitter_position(emitter: str) -> tuple[float, float]:
    # Ears sit either side of the listener, so a headset starts as a head-width pair
    if emitter.endswith(f"#{Side.LEFT.value}"):
        return (-EAR_SEPARATION, 0.0)
    if emitter.endswith(f"#{Side.RIGHT.value}"):
        return (EAR_SEPARATION, 0.0)

    return (0.0, 0.0)


def emitter_layout(
    sinks: list[str],
    headsets: set[str] | None = None,
    positions: dict[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    headsets = headsets or set()
    positions = positions or {}
    layout = {}

    for sink in sinks:
        for emitter in emitters_for(sink, sink in headsets):
            layout[emitter] = positions.get(emitter, default_emitter_position(emitter))

    return layout


def channel_gains(
    source: Any,
    sinks: list[str],
    positions: dict[str, tuple[float, float]] | None = None,
    headsets: set[str] | None = None,
) -> dict[str, tuple[float, float]]:
    """Per-sink left/right gains, panned by where each emitter sits relative to the source."""
    point = clamp_position(source)
    headsets = headsets or set()
    layout = emitter_layout(sinks, headsets, positions)
    gains = dbap_gains(point, layout)

    # With a single emitter there is no geometry to pan across, so balance provides the only cue
    lone = len(layout) == 1
    left, right = stereo_balance(point[0]) if lone else (1.0, 1.0)

    # A single device is max-normalised so enabling spatial never changes its overall level
    if len(sinks) == 1 and gains:
        loudest = max(gains.values())
        if loudest > 0:
            gains = {emitter: gain / loudest for emitter, gain in gains.items()}

    channels = {}
    for sink in sinks:
        if sink in headsets:
            channels[sink] = (
                round(gains.get(emitter_id(sink, Side.LEFT), 1.0), 6),
                round(gains.get(emitter_id(sink, Side.RIGHT), 1.0), 6),
            )
        else:
            gain = gains.get(emitter_id(sink), 1.0)
            channels[sink] = (round(gain * left, 6), round(gain * right, 6))

    return channels


def merge_positions(stored: Any, updates: dict[str, tuple[float, float]]) -> dict:
    """Positions are plugin-wide but a dialog only knows its own targets, so updates are merged."""
    merged = normalize_positions(stored)
    merged.update({k: clamp_position(v) for k, v in (updates or {}).items()})

    return merged
