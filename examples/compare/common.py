"""Shared constants and configuration for otelmini vs otel-python comparison tests."""

from pathlib import Path
from typing import Mapping, Optional, Sequence

# Span configuration - identical for both implementations
SPAN_NAME = "test-operation"
SPAN_ATTRIBUTES = {"test.key": "test-value", "test.count": 42}
EVENT_NAME = "test-event"
EVENT_ATTRIBUTES = {"event.key": "event-value"}

# Metrics configuration - identical for both implementations
COUNTER_NAME = "test-counter"
COUNTER_UNIT = "requests"
COUNTER_DESCRIPTION = "Test counter for comparison"
COUNTER_VALUE = 42


class BaseSpanCompareTest:
    """Base oteltest class for span comparison tests."""

    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_spans

        assert count_spans(tel) == 1, f"Expected 1 span, got {count_spans(tel)}"
        print(f"stdout:\n{stdout}")
        print(f"stderr:\n{stderr}")
        print(f"returncode: {returncode}")


# Keep old name for backwards compatibility
BaseCompareTest = BaseSpanCompareTest


class BaseRequestsAutoCompareTest:
    """Base oteltest class for requests auto-instrumentation comparison tests."""

    TARGET_URL = "https://httpbin.org/get"

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        return 10.0

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_spans

        span_count = count_spans(tel)
        assert span_count == 2, f"Expected 2 spans, got {span_count}"
        print(f"stdout:\n{stdout}")
        print(f"stderr:\n{stderr}")
        print(f"returncode: {returncode}")

    @staticmethod
    def run_instrumented_request():
        """Make an HTTP request with auto-instrumentation enabled."""
        import requests
        from opentelemetry import trace

        tracer = trace.get_tracer("requests-auto-compare-test")
        target = BaseRequestsAutoCompareTest.TARGET_URL

        with tracer.start_as_current_span("parent-operation") as span:
            span.set_attribute("test.target", target)
            response = requests.get(target)
            span.set_attribute("http.response.status_code", response.status_code)


class BaseMetricsCompareTest:
    """Base oteltest class for metrics comparison tests."""

    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        return 3.0

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_metrics, get_metric_names

        assert count_metrics(tel) >= 1, f"Expected at least 1 metric, got {count_metrics(tel)}"
        assert COUNTER_NAME in get_metric_names(tel), f"Expected {COUNTER_NAME} in metrics"
        print(f"stdout:\n{stdout}")
        print(f"stderr:\n{stderr}")
        print(f"returncode: {returncode}")
