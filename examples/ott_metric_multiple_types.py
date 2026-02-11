"""
Test that multiple metric types are exported together in a single export.
Creates Counter, UpDownCounter, Histogram, and Gauge instruments.
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

        assert len(tel.metric_requests) == 1, f"expected 1 export, got {len(tel.metric_requests)}"

        pbreq = MessageToDict(tel.metric_requests[0].pbreq)
        metrics_list = pbreq["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]

        # Should have 4 metrics
        assert len(metrics_list) == 4, f"expected 4 metrics, got {len(metrics_list)}"

        # Build a dict by metric name for easier assertions
        by_name = {m["name"]: m for m in metrics_list}

        # Counter - monotonic sum
        assert "requests" in by_name
        assert "sum" in by_name["requests"]
        assert by_name["requests"]["sum"]["isMonotonic"] is True
        assert int(by_name["requests"]["sum"]["dataPoints"][0]["asInt"]) == 100

        # UpDownCounter - non-monotonic sum
        assert "active_connections" in by_name
        assert "sum" in by_name["active_connections"]
        assert by_name["active_connections"]["sum"].get("isMonotonic", False) is False
        assert int(by_name["active_connections"]["sum"]["dataPoints"][0]["asInt"]) == 5

        # Histogram
        assert "response_time" in by_name
        assert "histogram" in by_name["response_time"]
        hist = by_name["response_time"]["histogram"]["dataPoints"][0]
        assert int(hist["count"]) == 3
        assert float(hist["sum"]) == 0.35  # 0.1 + 0.15 + 0.1

        # Gauge
        assert "temperature" in by_name
        assert "gauge" in by_name["temperature"]
        assert float(by_name["temperature"]["gauge"]["dataPoints"][0]["asDouble"]) == 72.5


if __name__ == "__main__":
    reader = ManualExportingMetricReader(HttpMetricExporter())
    provider = MeterProvider(metric_readers=(reader,))
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter("test-meter")

    # Counter
    counter = meter.create_counter("requests")
    counter.add(100)

    # UpDownCounter
    updown = meter.create_up_down_counter("active_connections")
    updown.add(10)
    updown.add(-5)  # Net: 5

    # Histogram
    histogram = meter.create_histogram("response_time")
    histogram.record(0.1)
    histogram.record(0.15)
    histogram.record(0.1)

    # Gauge
    gauge = meter.create_gauge("temperature")
    gauge.set(72.5)

    reader.force_flush()
