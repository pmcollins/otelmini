"""
Test auto-instrumentation with console exporters for all signals.
Sets OTEL_TRACES_EXPORTER=console, OTEL_METRICS_EXPORTER=console, OTEL_LOGS_EXPORTER=console.
"""

import logging
import time
from typing import Mapping, Optional, Sequence

from opentelemetry import trace, metrics

from _lib import package


class OtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {
            "OTEL_TRACES_EXPORTER": "console",
            "OTEL_METRICS_EXPORTER": "console",
            "OTEL_LOGS_EXPORTER": "console",
        }

    def requirements(self) -> Sequence[str]:
        return (package(),)

    def wrapper_command(self) -> str:
        return "otel"

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        return 5.0

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        # With console exporters, nothing goes to HTTP sink
        # Check stdout for JSON-OTLP output
        assert returncode == 0, f"script failed with return code {returncode}"

        # Should see trace output in stdout (JSON with resourceSpans)
        assert "resourceSpans" in stdout, "expected trace output in stdout"

        # Should see metric output in stdout (JSON with resourceMetrics)
        assert "resourceMetrics" in stdout, "expected metric output in stdout"

        # Should see log output in stdout (JSON with resourceLogs)
        assert "resourceLogs" in stdout, "expected log output in stdout"


if __name__ == "__main__":
    # Create a span
    tracer = trace.get_tracer("test-tracer")
    with tracer.start_as_current_span("test-span"):
        # Create a metric
        meter = metrics.get_meter("test-meter")
        counter = meter.create_counter("test_counter")
        counter.add(42)

        # Create a log
        logger = logging.getLogger("test")
        logger.warning("test log message")

    time.sleep(1)
