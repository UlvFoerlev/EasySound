from src.backend.PluginManager.ActionBase import ActionBase
from typing import Any


class SoundActionBase(ActionBase):
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

    def _set_property(self, key: str, value: Any) -> None:
        settings = self.get_settings()
        settings[key] = value
        self.set_settings(settings)
