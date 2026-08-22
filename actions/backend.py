from streamcontroller_plugin_tools import BackendBase
from pathlib import Path
from threading import Thread, Timer

try:
    import os

    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
    import pygame as pg
    from pygame.mixer import Sound, Channel
except ImportError as e:
    raise e


def file_stamp(path: str) -> tuple[float, int] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None

    return stat.st_mtime, stat.st_size


class Backend(BackendBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        pg.mixer.init()
        pg.mixer.set_num_channels(32)

        self.cached_sounds: dict[str, Sound] = {}
        self.cache_stamps: dict[str, tuple[float, int] | None] = {}

    def preload_sound(self, path: str | Path, force: bool = False) -> bool:
        key = path if isinstance(path, str) else str(path)
        stamp = file_stamp(key)

        # A cached sound is reused unless the file changed on disk, so a press never waits on decoding
        if not force and key in self.cached_sounds and self.cache_stamps.get(key) == stamp:
            return True

        try:
            self.cached_sounds[key] = pg.mixer.Sound(key)
        except (pg.error, OSError, TypeError, ValueError):
            self.cached_sounds.pop(key, None)
            self.cache_stamps.pop(key, None)
            return False

        self.cache_stamps[key] = stamp
        return True

    def warm_sound(self, path: str | Path) -> None:
        # Fire-and-forget so page loads and key presses never block on the first decode
        Thread(target=self.preload_sound, args=(path,), daemon=True).start()

    def play_sound(
        self,
        path: str | Path,
        volume: float = 100.0,
        loops: int = 0,
        fade_in: float = 0.0,
        fade_out: float = 0.0,
    ) -> tuple[Sound | None, Channel | None]:
        key = path if isinstance(path, str) else str(path)

        if not self.preload_sound(path=path):
            return None, None

        sound = self.cached_sounds[key]

        channel = pg.mixer.find_channel()
        if channel is None:
            return None, None

        # Volume is set per channel; Sound.set_volume would hit every action sharing the file
        channel.set_volume(max(min((volume / 100.0), 1.0), 0.0))
        channel.play(sound, loops=loops, fade_ms=int(fade_in * 1000))

        if fade_out and loops == 0:
            self.schedule_fade_out(channel=channel, sound=sound, fade_out=fade_out)

        return sound, channel

    def schedule_fade_out(self, channel: Channel, sound: Sound, fade_out: float) -> None:
        delay = max(sound.get_length() - fade_out, 0.0)

        timer = Timer(delay, self.fade_out_channel, args=(channel, sound, fade_out))
        timer.daemon = True
        timer.start()

    def fade_out_channel(self, channel: Channel, sound: Sound, fade_out: float) -> None:
        if channel.get_sound() == sound:  # the channel may have been recycled by now
            channel.fadeout(int(fade_out * 1000))


backend = Backend()
