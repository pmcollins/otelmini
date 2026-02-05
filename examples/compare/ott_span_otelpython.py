"""Span test using opentelemetry-python SDK - exports via HTTP/protobuf."""

import time
from pathlib import Path
from typing import Sequence

from common import (
    SPAN_NAME,
    SPAN_ATTRIBUTES,
    EVENT_NAME,
    EVENT_ATTRIBUTES,
    BaseCompareTest,
)


def create_test_span():
    """Create a single test span with attributes and an event."""
    # Import SDK here since it's installed by oteltest
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    exporter = OTLPSpanExporter()
    tp = TracerProvider()
    tp.add_span_processor(BatchSpanProcessor(exporter))
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


class SpanOtelpythonOtelTest(BaseCompareTest):
    def requirements(self) -> Sequence[str]:
        return (
            "opentelemetry-sdk",
            "opentelemetry-exporter-otlp-proto-http",
        )
