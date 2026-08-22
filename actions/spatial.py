import math
from typing import Any

# Distance added before the rolloff, so a source sitting on a speaker cannot produce an infinite gain
BLUR = 0.25
ROLLOFF = 2.0


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


def channel_gains(
    source: Any,
    sinks: list[str],
    positions: dict[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Final per-sink, per-channel gains: speaker placement combined with left/right balance."""
    point = clamp_position(source)
    positions = positions or {}

    # A sink with no saved position sits at the listener rather than being left out of the panning
    layout = {sink: positions.get(sink, (0.0, 0.0)) for sink in sinks}
    gains = dbap_gains(point, layout)
    left, right = stereo_balance(point[0])

    return {
        sink: (round(gain * left, 6), round(gain * right, 6))
        for sink, gain in gains.items()
    }
