from streamcontroller_plugin_tools import BackendBase

# from pydub import AudioSegment
from pydub.playback import play
from pathlib import Path
import pygame as pg, Sound


class Backend(BackendBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        pg.mixer.init()
        pg.init()

        self.cached_sounds: dict[str, Sound] = {}

    def cache_sound(self, path: str | Path):
        key = path if isinstance(path, str) else str(path)

        self.cached_sounds[key] = pg.mixer.Sound(path)

    def play_sound(self, path: str | Path):
        key = path if isinstance(path, str) else str(path)

        if key not in self.cached_sounds:
            self.cache_sound(path=path)

        self.cached_sounds[key].play()


backend = Backend()
