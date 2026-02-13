"""
Test observable instruments (ObservableGauge, ObservableCounter, ObservableUpDownCounter).
These use callbacks to provide values at collection time.
"""

from typing import Mapping, Optional, Sequence

from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation

from _lib import package
from otelmini.metric import (
    HttpMetricExporter,
    ManualExportingMetricReader,
    MeterProvider,
)

# Simulated state that callbacks will read
cpu_usage = 45.5
total_requests = 1000
active_tasks = 7


def cpu_callback(options: CallbackOptions):
    yield Observation(cpu_usage)


def requests_callback(options: CallbackOptions):
    yield Observation(total_requests)


def tasks_callback(options: CallbackOptions):
    yield Observation(active_tasks)


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

        # Should have 2 exports
        assert len(tel.metric_requests) == 2, f"expected 2 exports, got {len(tel.metric_requests)}"

        # First export - initial values
        pbreq1 = MessageToDict(tel.metric_requests[0].pbreq)
        metrics1 = {m["name"]: m for m in pbreq1["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]}

        assert "cpu_percent" in metrics1
        assert "gauge" in metrics1["cpu_percent"]
        assert float(metrics1["cpu_percent"]["gauge"]["dataPoints"][0]["asDouble"]) == 45.5

        assert "total_requests" in metrics1
        assert "sum" in metrics1["total_requests"]
        assert int(metrics1["total_requests"]["sum"]["dataPoints"][0]["asInt"]) == 1000

        assert "active_tasks" in metrics1
        assert "sum" in metrics1["active_tasks"]
        assert int(metrics1["active_tasks"]["sum"]["dataPoints"][0]["asInt"]) == 7

        # Second export - updated values
        pbreq2 = MessageToDict(tel.metric_requests[1].pbreq)
        metrics2 = {m["name"]: m for m in pbreq2["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]}

        assert float(metrics2["cpu_percent"]["gauge"]["dataPoints"][0]["asDouble"]) == 78.2
        assert int(metrics2["total_requests"]["sum"]["dataPoints"][0]["asInt"]) == 1500
        assert int(metrics2["active_tasks"]["sum"]["dataPoints"][0]["asInt"]) == 3


if __name__ == "__main__":
    reader = ManualExportingMetricReader(HttpMetricExporter())
    provider = MeterProvider(metric_readers=(reader,))
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter("test-meter")

    # Create observable instruments with callbacks
    meter.create_observable_gauge("cpu_percent", callbacks=[cpu_callback])
    meter.create_observable_counter("total_requests", callbacks=[requests_callback])
    meter.create_observable_up_down_counter("active_tasks", callbacks=[tasks_callback])

    # First export with initial values
    reader.force_flush()

    # Update values
    cpu_usage = 78.2
    total_requests = 1500
    active_tasks = 3

    # Second export with updated values
    reader.force_flush()
