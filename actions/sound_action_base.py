from src.backend.PluginManager.ActionCore import ActionCore
from typing import Any


class SoundActionBase(ActionCore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _get_property(
        self, key: str, default: Any = None, enforce_type: type | None = None
    ) -> Any:
        settings = self.get_settings()
        value = settings.get(key, default)

        if enforce_type and isinstance(value, enforce_type) is False:
            value = default

        return value
