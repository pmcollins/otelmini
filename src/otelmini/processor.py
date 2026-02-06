from __future__ import annotations

import atexit
import os
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable, Generic, List, Optional, Type, TypeVar

if TYPE_CHECKING:
    from otelmini._lib import Exporter

T = TypeVar("T")


class ForkAware(ABC):
    def register_at_fork(self) -> None:
        os.register_at_fork(after_in_child=self.reinitialize_at_fork)

    @abstractmethod
    def reinitialize_at_fork(self) -> None:
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
    """Batch processor with periodic export.

    Default values follow the OTel spec:
    - batch_size: 512 (OTEL_BSP_MAX_EXPORT_BATCH_SIZE)
    - interval_seconds: 5 (OTEL_BSP_SCHEDULE_DELAY = 5000ms)
    """

    def __init__(
        self,
        exporter: Exporter[T],
        batch_size: int = 512,
        interval_seconds: float = 5,
        batcher_factory: Optional[Type[Batcher[T]]] = None,
        timer_factory: Optional[Type[Timer]] = None,
    ):
        self.exporter = exporter
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._batcher_factory: Type[Batcher[T]] = batcher_factory or Batcher
        self._timer_factory: Type[Timer] = timer_factory or Timer

        self.batcher: Batcher[T] = self._batcher_factory(batch_size)
        self.stop = threading.Event()

        self.timer: Timer = self._timer_factory(self._export, interval_seconds)
        self.thread = threading.Thread(target=self.timer.run, daemon=True)
        self.thread.start()

        self.register_at_fork()

    def reinitialize_at_fork(self) -> None:
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

    def _export(self) -> None:
        batch = self.batcher.pop()
        if batch is not None and len(batch) > 0:
            self.exporter.export(batch)

    def shutdown(self) -> None:
        self.stop.set()
        self.timer.stop()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        self._export()
        return True


class Batcher(Generic[T]):
    def __init__(self, batch_size: int) -> None:
        self.lock = threading.RLock()
        self.batch_size = batch_size
        self.items: List[T] = []
        self.batches: List[List[T]] = []

    def add(self, item: T) -> bool:
        with self.lock:
            self.items.append(item)
            if len(self.items) == self.batch_size:
                self._batch()
                return True
            return False

    def pop(self) -> Optional[List[T]]:
        with self.lock:
            self._batch()
            return self.batches.pop(0) if len(self.batches) > 0 else None

    def _batch(self) -> None:
        self.batches.append(self.items)
        self.items = []


class Timer:
    def __init__(self, target_fcn: Callable[[], None], interval_seconds: float) -> None:
        self._target_fcn = target_fcn
        self._interval_seconds = interval_seconds
        self._sleeper = threading.Condition()
        self._stopper = threading.Event()

        atexit.register(self.stop)

    def run(self) -> None:
        while not self._stopper.is_set():
            self._sleep()
            if not self._stopper.is_set():
                self._target_fcn()

    def _sleep(self) -> None:
        with self._sleeper:
            self._sleeper.wait(self._interval_seconds)

    def notify_sleeper(self) -> None:
        with self._sleeper:
            self._sleeper.notify()

    def stop(self) -> None:
        self._stopper.set()
        self.notify_sleeper()
        self._target_fcn()
