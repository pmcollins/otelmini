"""
API-only ObservableGauge test using auto-instrumentation.
This script only imports from opentelemetry.* - no otelmini imports.
"""

import time
from typing import Mapping, Optional, Sequence

from opentelemetry import metrics
from opentelemetry.metrics import Observation

from _lib import package


# Simulated CPU usage value
_cpu_usage = 65.5


def cpu_callback():
    """Callback that returns simulated CPU usage."""
    return [Observation(value=_cpu_usage)]


if __name__ == '__main__':
    meter = metrics.get_meter("my-meter")
    gauge = meter.create_observable_gauge(
        "cpu_usage",
        callbacks=[cpu_callback],
        unit="%",
        description="CPU usage percentage"
    )
    time.sleep(1)


class ObservableGaugeOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return (package(),)

    def wrapper_command(self) -> str:
        return "otel"

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        return 3.0

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_metrics, get_metric_names, MessageToDict

        assert count_metrics(tel) == 1
        assert "cpu_usage" in get_metric_names(tel)

        # Access raw metric data (convert protobuf to dict)
        pbreq = MessageToDict(tel.metric_requests[0].pbreq)
        metric = pbreq["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
        assert metric["name"] == "cpu_usage"
        assert metric["unit"] == "%"
        assert metric["description"] == "CPU usage percentage"
        assert "gauge" in metric
        # Gauge should not have aggregationTemporality
        assert "aggregationTemporality" not in metric["gauge"]
        # Value from callback should be 65.5
        assert metric["gauge"]["dataPoints"][0]["asDouble"] == 65.5
