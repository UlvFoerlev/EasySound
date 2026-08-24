import os
from collections import OrderedDict
from pathlib import Path
from threading import RLock

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst

from .envelope import to_gain
from .playback import Playback, SoundPipeline

POOL_DEPTH = 2
MAX_PARKED = 32
START_TIMEOUT_MS = 250
VALIDATE_TIMEOUT_MS = 200


class _Pool:
    def __init__(self):
        self.idle: list[SoundPipeline] = []
        self.live: set[SoundPipeline] = set()


class SoundEngine:
    """Plays sounds through GStreamer, keeping decoders prerolled so presses never load."""

    def __init__(self, pool_depth: int = POOL_DEPTH, max_parked: int = MAX_PARKED):
        Gst.init_check(None)

        self.pool_depth = pool_depth
        self.max_parked = max_parked
        self._pools: OrderedDict[str, _Pool] = OrderedDict()
        self._lock = RLock()

    def preload(self, path: str | Path) -> None:
        key = str(path)
        if not key or not os.path.isfile(key):
            return

        with self._lock:
            pool = self._pool(key)
            missing = self.pool_depth - len(pool.idle) - len(pool.live)

            for _ in range(max(missing, 0)):
                pipeline = self._create(key)
                if pipeline is None:
                    return

                pool.idle.append(pipeline)

            self._evict()

    def validate(self, path: str | Path, timeout_ms: int = VALIDATE_TIMEOUT_MS) -> bool:
        key = str(path)
        if not key or not os.path.isfile(key):
            return False

        self.preload(key)

        with self._lock:
            pool = self._pools.get(key)
            candidate = pool.idle[0] if pool and pool.idle else None

        if candidate is None:
            return False

        # A preroll still in flight is not proof of a bad file, so only errors count against it
        return candidate.wait_ready(timeout_ms) or not candidate.failed

    def play(
        self,
        path: str | Path,
        volume: float = 100.0,
        loops: int = 0,
        fade_in: float = 0.0,
        fade_out: float = 0.0,
    ) -> Playback | None:
        key = str(path)
        if not key or not os.path.isfile(key):
            return None

        with self._lock:
            pool = self._pool(key)
            pipeline = pool.idle.pop() if pool.idle else self._create(key)

            if pipeline is None:
                return None

            pool.live.add(pipeline)

        if not pipeline.wait_ready(START_TIMEOUT_MS) and pipeline.failed:
            self._discard(pipeline)
            return None

        token = pipeline.start(to_gain(volume), loops, fade_in, fade_out)

        with self._lock:
            self._top_up(key)

        return Playback(pipeline, token)

    def forget(self, path: str | Path) -> None:
        key = str(path)

        with self._lock:
            pool = self._pools.pop(key, None)

        if pool is None:
            return

        for pipeline in pool.idle:
            pipeline.dispose()

    def shutdown(self) -> None:
        with self._lock:
            pools = list(self._pools.values())
            self._pools.clear()

        for pool in pools:
            for pipeline in list(pool.idle) + list(pool.live):
                pipeline.dispose()

    def _pool(self, key: str) -> _Pool:
        pool = self._pools.get(key)

        if pool is None:
            pool = _Pool()
            self._pools[key] = pool

        self._pools.move_to_end(key)

        return pool

    def _create(self, key: str) -> SoundPipeline | None:
        try:
            pipeline = SoundPipeline(path=key, devices=[None], on_idle=self._on_idle)
        except Exception:
            return None

        # Armed on creation so play() can block on the preroll and read the duration
        pipeline.arm()

        return pipeline

    def _top_up(self, key: str) -> None:
        pool = self._pools.get(key)
        if pool is None or pool.idle:
            return

        pipeline = self._create(key)
        if pipeline is None:
            return

        pool.idle.append(pipeline)
        self._evict()

    def _on_idle(self, pipeline: SoundPipeline) -> None:
        with self._lock:
            pool = self._pools.get(pipeline.path)

            if pool is None:
                pipeline.dispose()
                return

            pool.live.discard(pipeline)

            if pipeline.failed or len(pool.idle) >= self.pool_depth:
                pipeline.dispose()
                return

            pool.idle.append(pipeline)
            self._evict()

    def _discard(self, pipeline: SoundPipeline) -> None:
        with self._lock:
            pool = self._pools.get(pipeline.path)
            if pool is not None:
                pool.live.discard(pipeline)

        pipeline.dispose()

    def _evict(self) -> None:
        """Parked pipelines hold a corked server stream each, so cap how many idle at once."""
        parked = sum(len(pool.idle) for pool in self._pools.values())

        for key in list(self._pools):
            while parked > self.max_parked and self._pools[key].idle:
                self._pools[key].idle.pop(0).dispose()
                parked -= 1

            if parked <= self.max_parked:
                return
