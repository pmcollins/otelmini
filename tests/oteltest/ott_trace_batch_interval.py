"""
Test that BatchProcessor exports when interval_seconds elapses.
Creates 12 spans over ~6 seconds with interval_seconds=2, so we expect
multiple interval-triggered exports before shutdown.
"""

import time
from typing import Mapping, Optional, Sequence

from opentelemetry import trace

from _lib import package
from otelmini.processor import BatchProcessor
from otelmini.trace import HttpSpanExporter, MiniTracerProvider


class OtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return (package(),)

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        return None

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_spans

        # Should have received all 12 spans
        assert count_spans(tel) == 12, f"expected 12 spans, got {count_spans(tel)}"

        # Should have multiple exports (interval triggered + shutdown)
        # With 12 spans at 0.5s each = 6s total, and 2s interval,
        # we expect around 3-4 exports (timing dependent)
        num_exports = len(tel.trace_requests)
        assert num_exports >= 2, f"expected at least 2 exports, got {num_exports}"


if __name__ == "__main__":
    tp = MiniTracerProvider(
        BatchProcessor(
            HttpSpanExporter(),
            batch_size=1000,  # Won't hit batch size
            interval_seconds=2,
        )
    )
    trace.set_tracer_provider(tp)
    tracer = trace.get_tracer(__name__)

    # Create 12 spans slowly - should trigger interval exports
    for i in range(12):
        with tracer.start_as_current_span(f"span-{i}"):
            time.sleep(0.5)
