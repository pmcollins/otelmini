from __future__ import annotations

import atexit
import logging
import os
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from otelmini._lib import Exporter

_pylogger = logging.getLogger(__package__)

T = TypeVar("T")


class ForkAware(ABC):
    def register_at_fork(self):
        os.register_at_fork(after_in_child=self.reinitialize_at_fork)

    @abstractmethod
    def reinitialize_at_fork(self):
        pass


class Processor(ABC, Generic[T]):
    """Base processor interface for telemetry items.

    Subclasses can override on_start and/or on_end as needed.
    Default implementations are no-ops.
    """

    def on_start(self, item: T) -> None:
        """Called when an item starts. Default is a no-op."""
        pass

    def on_end(self, item: T) -> None:
        """Called when an item ends. Default is a no-op."""
        pass


class BatchProcessor(Processor[T], ForkAware):
    def __init__(
        self,
        exporter: Exporter,
        batch_size,
        interval_seconds,
        batcher_factory=None,
        timer_factory=None,
    ):
        self.exporter = exporter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._batcher_factory = batcher_factory or Batcher
        self._timer_factory = timer_factory or Timer

        self.batcher = self._batcher_factory(batch_size)
        self.stop = threading.Event()

        self.timer = self._timer_factory(self._export, interval_seconds)
        self.thread = threading.Thread(target=self.timer.run, daemon=True)
        self.thread.start()

        self.register_at_fork()

    def reinitialize_at_fork(self):
        self.shutdown()

        self.stop.clear()
        self.batcher = self._batcher_factory(self._batch_size)

        self.timer = self._timer_factory(self._export, self._interval_seconds)
        self.thread = threading.Thread(target=self.timer.run, daemon=True)
        self.thread.start()

    def on_end(self, item: T) -> None:
        if not self.stop.is_set():
            batched = self.batcher.add(item)
            if batched:
                self.timer.notify_sleeper()

    def _export(self):
        batch = self.batcher.pop()
        if batch is not None and len(batch) > 0:
            self.exporter.export(batch)

    def shutdown(self) -> None:
        self.stop.set()
        self.timer.stop()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        self._export()
        return True


class Batcher:
    def __init__(self, batch_size):
        self.lock = threading.RLock()
        self.batch_size = batch_size
        self.items = []
        self.batches = []

    def add(self, item):
        with self.lock:
            self.items.append(item)
            if len(self.items) == self.batch_size:
                self._batch()
                return True
            return False

    def pop(self):
        with self.lock:
            self._batch()
            return self.batches.pop(0) if len(self.batches) > 0 else None

    def _batch(self):
        self.batches.append(self.items)
        self.items = []


class Timer:
    def __init__(self, target_fcn, interval_seconds):
        self._target_fcn = target_fcn
        self._interval_seconds = interval_seconds
        self._sleeper = threading.Condition()
        self._stopper = threading.Event()

        atexit.register(self.stop)

    def run(self):
        while not self._stopper.is_set():
            self._sleep()
            if not self._stopper.is_set():
                self._target_fcn()

    def _sleep(self):
        with self._sleeper:
            self._sleeper.wait(self._interval_seconds)

    def notify_sleeper(self):
        with self._sleeper:
            self._sleeper.notify()

    def stop(self):
        self._stopper.set()
        self.notify_sleeper()
        self._target_fcn()
