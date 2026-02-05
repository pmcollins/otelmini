"""
API-only metrics test using auto-instrumentation.
This script only imports from opentelemetry.* - no otelmini imports.
"""

import time
from pathlib import Path
from typing import Mapping, Optional, Sequence

from opentelemetry import metrics


def main():
    # Get meter via API - SDK is set up by auto-instrumentation
    meter = metrics.get_meter("my-meter")

    # Create a counter
    counter = meter.create_counter("requests", unit="1", description="Total requests")
    counter.add(42)

    # Give time for periodic export
    time.sleep(2)


if __name__ == "__main__":
    main()


class AutoMetricsOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        parent = str(Path(__file__).resolve().parent.parent)
        return (parent,)

    def wrapper_command(self) -> str:
        return "otel"

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        return 6.0  # Wait for periodic export

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_metrics, get_metric_names

        assert count_metrics(tel) >= 1, f"Expected at least 1 metric, got {count_metrics(tel)}"
        assert "requests" in get_metric_names(tel), f"Expected 'requests' metric, got {get_metric_names(tel)}"
