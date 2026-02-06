import threading
import time
from typing import List, Sequence

from otelmini.export import Exporter, ExportResult
from otelmini.processor import BatchProcessor, Batcher, Timer
from tests._lib import mk_span


class FakeExporter(Exporter):
    """Exporter that records all exports for verification."""

    def __init__(self):
        self.exports: List[List] = []
        self.export_count = 0

    def export(self, items: Sequence) -> ExportResult:
        self.exports.append(list(items))
        self.export_count += 1
        return ExportResult.SUCCESS


class FakeTimer:
    """Timer that doesn't actually run, for testing BatchProcessor without threading."""

    def __init__(self, target_fcn, interval_seconds):
        self.target_fcn = target_fcn
        self.interval_seconds = interval_seconds
        self.notify_count = 0

    def run(self):
        pass  # Don't actually run

    def notify_sleeper(self):
        self.notify_count += 1

    def stop(self):
        self.target_fcn()  # Final export on stop


def test_batch_processor_exports_on_batch_full():
    """When batch is full, export is triggered."""
    exporter = FakeExporter()
    processor = BatchProcessor(
        exporter,
        batch_size=2,
        interval_seconds=9999,  # Long interval so timer doesn't interfere
        timer_factory=FakeTimer,
    )

    span1 = mk_span("span1")
    span2 = mk_span("span2")

    processor.on_end(span1)
    assert exporter.export_count == 0  # Not exported yet

    processor.on_end(span2)
    # Batch is full, but export happens on timer notify, not immediately
    # The FakeTimer.notify_sleeper was called
    assert processor.timer.notify_count == 1

    processor.shutdown()


def test_batch_processor_exports_on_shutdown():
    """Incomplete batch is exported on shutdown."""
    exporter = FakeExporter()
    processor = BatchProcessor(
        exporter,
        batch_size=100,  # Large batch so it won't fill
        interval_seconds=9999,
        timer_factory=FakeTimer,
    )

    span = mk_span("single-span")
    processor.on_end(span)

    assert exporter.export_count == 0  # Not exported yet

    processor.shutdown()

    assert exporter.export_count == 1
    assert len(exporter.exports[0]) == 1
    assert exporter.exports[0][0].get_name() == "single-span"


def test_batch_processor_force_flush():
    """force_flush exports current batch."""
    exporter = FakeExporter()
    processor = BatchProcessor(
        exporter,
        batch_size=100,
        interval_seconds=9999,
        timer_factory=FakeTimer,
    )

    processor.on_end(mk_span("span1"))
    processor.on_end(mk_span("span2"))

    assert exporter.export_count == 0

    processor.force_flush()

    assert exporter.export_count == 1
    assert len(exporter.exports[0]) == 2

    processor.shutdown()


def test_batch_processor_periodic_export():
    """Single span is exported after interval without explicit flush."""
    exporter = FakeExporter()
    export_event = threading.Event()

    class NotifyingExporter(Exporter):
        def __init__(self, inner):
            self.inner = inner

        def export(self, items):
            result = self.inner.export(items)
            export_event.set()
            return result

    notifying_exporter = NotifyingExporter(exporter)

    processor = BatchProcessor(
        notifying_exporter,
        batch_size=100,  # Large batch so it won't trigger batch-full export
        interval_seconds=0.1,  # Short interval for fast test
    )

    # Add a single span (won't trigger batch-full export)
    processor.on_end(mk_span("periodic-span"))

    # Wait for periodic export (with timeout)
    exported = export_event.wait(timeout=2.0)

    assert exported, "Span was not exported within timeout"
    assert exporter.export_count >= 1
    assert any(
        len(batch) > 0 and batch[0].get_name() == "periodic-span"
        for batch in exporter.exports
    )

    processor.shutdown()


def test_batch_processor_default_values():
    """BatchProcessor has sensible defaults."""
    exporter = FakeExporter()
    processor = BatchProcessor(exporter, timer_factory=FakeTimer)

    assert processor._batch_size == 512
    assert processor._interval_seconds == 5

    processor.shutdown()


def test_batcher_batches_at_size():
    """Batcher creates a batch when size is reached."""
    batcher = Batcher(batch_size=3)

    assert batcher.add("a") is False
    assert batcher.add("b") is False
    assert batcher.add("c") is True  # Batch full

    batch = batcher.pop()
    assert batch == ["a", "b", "c"]


def test_batcher_pop_flushes_partial():
    """Batcher.pop() returns partial batch."""
    batcher = Batcher(batch_size=10)

    batcher.add("a")
    batcher.add("b")

    batch = batcher.pop()
    assert batch == ["a", "b"]

    # Second pop returns empty list
    assert batcher.pop() == []


def test_timer_calls_target_periodically():
    """Timer calls target function after interval."""
    call_count = 0
    call_event = threading.Event()

    def target():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            call_event.set()

    timer = Timer(target, interval_seconds=0.05)
    thread = threading.Thread(target=timer.run, daemon=True)
    thread.start()

    # Wait for at least 2 calls
    call_event.wait(timeout=2.0)
    timer.stop()

    assert call_count >= 2
