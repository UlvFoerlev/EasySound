from GtkHelper.GenerativeUI.SpinRow import SpinRow
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.EventAssigner import EventAssigner

from ..sound_action_base import SoundActionBase


class StopAllAction(SoundActionBase):
    """Stops every sound this plugin is playing, whatever action or page started it."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_event_assigner(
            EventAssigner(
                id="stop_all_pressed",
                ui_label=self.plugin_base.lm.get("action.play-sound.event.pressed"),
                default_events=[Input.Key.Events.DOWN, Input.Dial.Events.DOWN],
                callback=self.on_pressed,
            )
        )

    @property
    def fade_out(self) -> float:
        return self._get_property(key="fade_out", default=0.0, enforce_type=float)

    def get_config_rows(self):
        # generative_ui_objects is never cleared upstream, so rebuild it to avoid duplicated rows
        self.generative_ui_objects.clear()

        self.fade_out_row = SpinRow(
            action_core=self,
            var_name="fade_out",
            default_value=0.0,
            min=0,
            max=10,
            step=0.05,
            digits=2,
            title="action.stop-all.fade-out.title",
            subtitle="action.stop-all.fade-out.subtitle",
        )

        # The framework adds every auto_add row itself, so returning them here would double-parent them
        return []

    def on_pressed(self, data) -> None:
        backend = getattr(self.plugin_base, "backend", None)
        if backend is None:
            self.show_error(duration=2)
            return

        try:
            backend.stop_all(self.fade_out)
        except Exception:  # rpyc reraises backend and connection faults as arbitrary types
            self.show_error(duration=2)
