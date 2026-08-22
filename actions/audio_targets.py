import uuid
from typing import Any

DEFAULT = "default"
ALL = "all"
CUSTOM = "custom"
SINK_PREFIX = "sink:"
GROUP_PREFIX = "group:"


def target_value(value: Any) -> str:
    """ComboRow hands its callbacks item objects, while everything else here works on the stored string."""
    getter = getattr(value, "get_value", None)
    if callable(getter):
        value = getter()

    return value if isinstance(value, str) else ""


def format_sink_target(sink_name: str) -> str:
    return f"{SINK_PREFIX}{sink_name}"


def format_group_target(group_id: str) -> str:
    return f"{GROUP_PREFIX}{group_id}"


def normalize_groups(raw: Any) -> list[dict]:
    # Saved settings are user-editable json, so anything malformed is dropped rather than raising
    if not isinstance(raw, list):
        return []

    groups = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue

        group_id = entry.get("id")
        name = entry.get("name")
        sinks = entry.get("sinks")
        if not isinstance(group_id, str) or not group_id:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(sinks, list):
            continue

        groups.append(
            {
                "id": group_id,
                "name": name.strip(),
                "sinks": [s for s in sinks if isinstance(s, str) and s],
            }
        )

    return groups


def find_group(groups: list[dict], group_id: str) -> dict | None:
    for group in groups:
        if group["id"] == group_id:
            return group

    return None


def resolve_target(
    target: str,
    available: list[str],
    groups: list[dict] | None = None,
) -> list[str] | None:
    """Returns the sinks to play on, or None to mean "let the server pick its default"."""
    groups = groups or []

    if not target or target == DEFAULT or target == CUSTOM:
        return None

    if target == ALL:
        return list(available)

    if target.startswith(SINK_PREFIX):
        sink = target[len(SINK_PREFIX) :]
        # Resolved against what exists right now, so a disconnected speaker is simply absent
        return [sink] if sink in available else []

    if target.startswith(GROUP_PREFIX):
        group = find_group(groups, target[len(GROUP_PREFIX) :])
        if group is None:
            return []
        return [sink for sink in group["sinks"] if sink in available]

    return None


def missing_sinks(target: str, available: list[str], groups: list[dict] | None = None) -> list[str]:
    """Members a saved selection refers to that are not currently present."""
    groups = groups or []

    if target.startswith(SINK_PREFIX):
        sink = target[len(SINK_PREFIX) :]
        return [] if sink in available else [sink]

    if target.startswith(GROUP_PREFIX):
        group = find_group(groups, target[len(GROUP_PREFIX) :])
        if group is None:
            return []
        return [sink for sink in group["sinks"] if sink not in available]

    return []


def new_group_id() -> str:
    return uuid.uuid4().hex


def upsert_group(groups: list[dict], group_id: str, name: str, sinks: list[str]) -> list[dict]:
    entry = {"id": group_id, "name": name.strip(), "sinks": list(sinks)}
    updated = [dict(group) for group in groups]

    for index, group in enumerate(updated):
        if group["id"] == group_id:
            updated[index] = entry
            return updated

    updated.append(entry)
    return updated


def delete_group(groups: list[dict], group_id: str) -> list[dict]:
    return [dict(group) for group in groups if group["id"] != group_id]
