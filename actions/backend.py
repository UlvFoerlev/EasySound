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

    def play_sound(
        self,
        path: str | Path,
        volume: float = 100.0,
        loops: int = 0,
        fade_in: float = 0.0,
        fade_out: float = 0.0,
    ):
        key = path if isinstance(path, str) else str(path)

        if key not in self.cached_sounds:
            self.cache_sound(path=path)

        sound = self.cached_sounds[key]
        real_volume = max(min((volume / 100.0), 1.0), 0.0)
        sound.set_volume(real_volume)
        channel = sound.play(loops=loops, fade_ms=int(fade_in * 1000))
        sound.fadeout(int(fade_out * 1000))

        return sound, channel


backend = Backend()
