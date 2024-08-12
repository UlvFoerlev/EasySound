from streamcontroller_plugin_tools import BackendBase
from pathlib import Path
import pygame as pg
from pygame.mixer import Sound


class Backend(BackendBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        pg.mixer.init()
        pg.init()

        self.cached_sounds: dict[str, Sound] = {}

    def cache_sound(self, path: str | Path):
        key = path if isinstance(path, str) else str(path)

        self.cached_sounds[key] = pg.mixer.Sound(path)

    def play_sound(self, path: str | Path, volume: float = 100.0):
        key = path if isinstance(path, str) else str(path)

        if key not in self.cached_sounds:
            self.cache_sound(path=path)

        sound = self.cached_sounds[key]
        real_volume = max(min((volume / 100.0), 1.0), 0.0)
        sound.set_volume(value=real_volume)
        sound.play()


backend = Backend()
