"""Span test using otelmini - exports via HTTP/JSON."""

import time
from pathlib import Path
from typing import Sequence

from opentelemetry import trace

from otelmini.processor import BatchProcessor
from otelmini.trace import HttpSpanExporter, MiniTracerProvider

from common import (
    SPAN_NAME,
    SPAN_ATTRIBUTES,
    EVENT_NAME,
    EVENT_ATTRIBUTES,
    BaseSpanCompareTest,
)


def create_test_span():
    """Create a single test span with attributes and an event."""
    tp = MiniTracerProvider(BatchProcessor(HttpSpanExporter(), batch_size=1, interval_seconds=1))
    trace.set_tracer_provider(tp)
    tracer = trace.get_tracer("compare-test")

    with tracer.start_as_current_span(SPAN_NAME) as span:
        for key, value in SPAN_ATTRIBUTES.items():
            span.set_attribute(key, value)
        span.add_event(EVENT_NAME, EVENT_ATTRIBUTES)
        time.sleep(0.1)  # Simulate some work

    tp.shutdown()


if __name__ == "__main__":
    create_test_span()


class SpanOtelminiOtelTest(BaseSpanCompareTest):
    def requirements(self) -> Sequence[str]:
        # otelmini package (parent of examples dir)
        parent = str(Path(__file__).resolve().parent.parent.parent)
        return (parent,)
