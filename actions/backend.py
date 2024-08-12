from streamcontroller_plugin_tools import BackendBase
from pydub import AudioSegment
from pydub.playback import play
from pathlib import Path


class Backend(BackendBase):
    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)

        self.cached_sounds: dict[str, AudioSegment] = {}

    def cache_sound(self, path: str | Path):
        key = path if isinstance(path, str) else str(path)

        self.cached_sounds[key] = AudioSegment.from_wav(path)

    def play_sound(self, path: str | Path):
        key = path if isinstance(path, str) else str(path)

        if key not in self.cached_sounds:
            self.cache_sound(path=path)

        play(self.cached_sounds[key])


backend = Backend()
