"""
Test that BatchProcessor exports when batch_size is reached.
Creates 36 spans with batch_size=24, so we expect:
- 1 export triggered by batch size (24 spans)
- 1 export on shutdown (12 spans)
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
        from oteltest.telemetry import count_spans, MessageToDict

        # Should have received all 36 spans
        assert count_spans(tel) == 36, f"expected 36 spans, got {count_spans(tel)}"

        # Should have 2 trace requests (exports)
        assert len(tel.trace_requests) == 2, f"expected 2 exports, got {len(tel.trace_requests)}"

        # First export should have 24 spans (batch size trigger)
        req1 = MessageToDict(tel.trace_requests[0].pbreq)
        spans1 = req1["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans1) == 24, f"first export: expected 24 spans, got {len(spans1)}"

        # Second export should have 12 spans (shutdown flush)
        req2 = MessageToDict(tel.trace_requests[1].pbreq)
        spans2 = req2["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans2) == 12, f"second export: expected 12 spans, got {len(spans2)}"


if __name__ == "__main__":
    tp = MiniTracerProvider(
        BatchProcessor(
            HttpSpanExporter(),
            batch_size=24,
            interval_seconds=600,  # 10 min - won't fire during test
        )
    )
    trace.set_tracer_provider(tp)
    tracer = trace.get_tracer(__name__)

    # Create 36 spans quickly - should trigger batch export at 24
    for i in range(36):
        with tracer.start_as_current_span(f"span-{i}"):
            time.sleep(0.05)
