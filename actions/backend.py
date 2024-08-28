
from pygame.mixer import Sound, Channel
import pygame as pg
from pathlib import Path
from streamcontroller_plugin_tools import BackendBase


class EasySoundError(Exception):
    pass


class InvalidSoundFileError(EasySoundError):
    pass


class Backend(BackendBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        pg.mixer.init()
        pg.init()

        self.cached_sounds: dict[str, Sound] = {}

    def cache_sound(self, path: str | Path):
        key = path if isinstance(path, str) else str(path)

        try:
            self.cached_sounds[key] = pg.mixer.Sound(path)
        except pg.error:
            raise InvalidSoundFileError(f"Invalid filetype {key}.")

    def play_sound(
        self,
        path: str | Path,
        volume: float = 100.0,
        loops: int = 0,
        fade_in: float = 0.0,
        immediate_fade_out: float = 0.0,
    ) -> tuple[Sound | None, Channel | None]:
        key = path if isinstance(path, str) else str(path)

        if key not in self.cached_sounds:
            try:
                self.cache_sound(path=path)
            except InvalidSoundFileError:
                return None, None

        sound = self.cached_sounds[key]
        real_volume = max(min((volume / 100.0), 1.0), 0.0)
        sound.set_volume(real_volume)
        channel = sound.play(loops=loops, fade_ms=int(fade_in * 1000))
        if immediate_fade_out:
            sound.fadeout(int(immediate_fade_out * 1000))

        return sound, channel


backend = Backend()
