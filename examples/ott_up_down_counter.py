import time
from pathlib import Path
from typing import Mapping, Optional, Sequence

from otelmini.metric import ManualExportingMetricReader, MeterProvider, HttpMetricExporter

if __name__ == '__main__':
    exporter = HttpMetricExporter()
    reader = ManualExportingMetricReader(exporter=exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter("my-meter")
    up_down_counter = meter.create_up_down_counter("connections", unit="1", description="Active connections")
    up_down_counter.add(10)
    up_down_counter.add(-3)  # Test decrement
    time.sleep(1)
    reader.force_flush()
    time.sleep(1)


class UpDownCounterOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        parent = str(Path(__file__).resolve().parent.parent)
        return (parent,)

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_metrics, get_metric_names, MessageToDict

        assert count_metrics(tel) == 1
        assert "connections" in get_metric_names(tel)

        # Access raw metric data (convert protobuf to dict)
        pbreq = MessageToDict(tel.metric_requests[0].pbreq)
        metric = pbreq["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
        assert metric["name"] == "connections"
        assert metric["unit"] == "1"
        assert metric["description"] == "Active connections"
        assert "sum" in metric
        assert metric["sum"]["aggregationTemporality"] == "AGGREGATION_TEMPORALITY_CUMULATIVE"
        # UpDownCounter should be non-monotonic (isMonotonic absent or False)
        assert metric["sum"].get("isMonotonic", False) is False
        # Value should be 10 + (-3) = 7
        assert metric["sum"]["dataPoints"][0]["asDouble"] == 7.0
