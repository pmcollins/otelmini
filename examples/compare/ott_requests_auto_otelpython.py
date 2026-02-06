"""Requests instrumentation test using opentelemetry-python auto-instrumentation."""

from typing import Mapping, Optional, Sequence

from opentelemetry import trace


TARGET_URL = "https://httpbin.org/get"


def run_instrumented_request():
    """Make an HTTP request with auto-instrumentation enabled."""
    import requests

    tracer = trace.get_tracer("requests-auto-compare-test")

    # Make a request inside a parent span
    with tracer.start_as_current_span("parent-operation") as span:
        span.set_attribute("test.target", TARGET_URL)
        response = requests.get(TARGET_URL)
        span.set_attribute("http.response.status_code", response.status_code)


if __name__ == "__main__":
    run_instrumented_request()


class RequestsAutoOtelpythonOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        }

    def requirements(self) -> Sequence[str]:
        return (
            "opentelemetry-distro",
            "opentelemetry-exporter-otlp",
            "requests",
            "opentelemetry-instrumentation-requests",
        )

    def wrapper_command(self) -> str:
        return "opentelemetry-instrument"

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
