"""Lambda function using otelmini for tracing."""

import time

_import_start = time.perf_counter()

import json

from opentelemetry import trace

from otelmini.processor import BatchProcessor
from otelmini.trace import HttpSpanExporter, MiniTracerProvider

_import_time_ms = (time.perf_counter() - _import_start) * 1000

# Setup tracing
_setup_start = time.perf_counter()
provider = MiniTracerProvider(BatchProcessor(HttpSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)
_setup_time_ms = (time.perf_counter() - _setup_start) * 1000

_total_init_ms = _import_time_ms + _setup_time_ms


def handler(event, context):
    """Lambda handler that creates a span and returns timing info."""
    span_start = time.perf_counter()

    with tracer.start_as_current_span("lambda-invocation") as span:
        span.set_attribute("event.test", event.get("test", False))

        # Simulate some work
        with tracer.start_as_current_span("process-event"):
            result = {"processed": True}

    span_time_ms = (time.perf_counter() - span_start) * 1000

    return {
        "statusCode": 200,
        "body": json.dumps({
            "library": "otelmini",
            "timing": {
                "import_ms": round(_import_time_ms, 2),
                "setup_ms": round(_setup_time_ms, 2),
                "total_init_ms": round(_total_init_ms, 2),
                "span_creation_ms": round(span_time_ms, 2),
            },
            "result": result,
        }),
    }
