"""
Test that ManualExportingMetricReader exports on force_flush().
"""

from typing import Mapping, Optional, Sequence

from opentelemetry import metrics

from _lib import package
from otelmini.metric import (
    HttpMetricExporter,
    ManualExportingMetricReader,
    MeterProvider,
)


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
        from oteltest.telemetry import MessageToDict

        # Should have exactly 3 exports (one per force_flush call)
        assert len(tel.metric_requests) == 3, f"expected 3 exports, got {len(tel.metric_requests)}"

        # Verify counter values at each export point
        for i, req in enumerate(tel.metric_requests):
            pbreq = MessageToDict(req.pbreq)
            metric = pbreq["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
            assert metric["name"] == "items_processed"
            # Cumulative counter: values should be 10, 25, 50
            expected_values = [10, 25, 50]
            actual = int(metric["sum"]["dataPoints"][0]["asInt"])
            assert actual == expected_values[i], f"export {i}: expected {expected_values[i]}, got {actual}"


if __name__ == "__main__":
    reader = ManualExportingMetricReader(HttpMetricExporter())
    provider = MeterProvider(metric_readers=(reader,))
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter("test-meter")
    counter = meter.create_counter("items_processed")

    # Add 10, flush
    counter.add(10)
    reader.force_flush()

    # Add 15 more (total 25), flush
    counter.add(15)
    reader.force_flush()

    # Add 25 more (total 50), flush
    counter.add(25)
    reader.force_flush()
