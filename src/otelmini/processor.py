from __future__ import annotations

import atexit
import logging
import multiprocessing
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, Sequence, TypeVar

if TYPE_CHECKING:
    from otelmini._grpclib import GrpcExportResult

_pylogger = logging.getLogger(__package__)

# Generic type for different signal types
T = TypeVar("T")


class Processor(ABC, Generic[T]):
    @abstractmethod
    def on_start(self, item: T) -> None:
        pass

    @abstractmethod
    def on_end(self, item: T) -> None:
        pass


def foo():
    pass

class ForkingBatchProcessor(Processor[T]):
    def __init__(self, exporter: Exporter[T], batch_size, interval_seconds):
        self.exporter = exporter
        self.q = multiprocessing.Queue()
        self.proc = multiprocessing.Process(target=foo, daemon=True)

    def on_start(self, item: T) -> None:
        pass

    def on_end(self, item: T) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class BatchProcessor(Processor[T]):
    def __init__(self, exporter: Exporter[T], batch_size, interval_seconds):
        self.exporter = exporter
        self.batcher = Batcher(batch_size)
        self.stop = threading.Event()

        self.timer = Timer(self._export, interval_seconds)
        self.thread = threading.Thread(target=self.timer.run, daemon=True)
        self.thread.start()

    def on_start(self, item: T) -> None:
        pass

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


class Exporter(ABC, Generic[T]):
    @abstractmethod
    def export(self, items: Sequence[T]) -> GrpcExportResult:
        pass
