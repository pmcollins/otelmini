"""Requests instrumentation test using opentelemetry-python SDK - exports via HTTP/protobuf."""

from pathlib import Path
from typing import Mapping, Optional, Sequence


TARGET_URL = "https://httpbin.org/get"


def run_instrumented_request():
    """Make an HTTP request with instrumentation enabled."""
    import requests
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    # Set up otel-python tracing
    exporter = OTLPSpanExporter()
    tp = TracerProvider()
    tp.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(tp)

    # Instrument requests library
    RequestsInstrumentor().instrument()

    tracer = trace.get_tracer("requests-compare-test")

    # Make a request inside a parent span
    with tracer.start_as_current_span("parent-operation") as span:
        span.set_attribute("test.target", TARGET_URL)
        response = requests.get(TARGET_URL)
        span.set_attribute("http.response.status_code", response.status_code)

    tp.shutdown()


if __name__ == "__main__":
    run_instrumented_request()


class RequestsOtelpythonOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return (
            "opentelemetry-sdk",
            "opentelemetry-exporter-otlp-proto-http",
            "requests",
            "opentelemetry-instrumentation-requests",
        )

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        return 10.0  # Allow time for HTTP request

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_spans

        # Expect 2 spans: parent + HTTP request
        span_count = count_spans(tel)
        assert span_count == 2, f"Expected 2 spans, got {span_count}"
        print(f"stdout:\n{stdout}")
        print(f"stderr:\n{stderr}")
        print(f"returncode: {returncode}")
