"""
API-only counter test using auto-instrumentation.
This script only imports from opentelemetry.* - no otelmini imports.
"""

import time
from typing import Mapping, Optional, Sequence

from opentelemetry import metrics

from _lib import package


if __name__ == '__main__':
    meter = metrics.get_meter("my-meter")
    counter = meter.create_counter("x")
    counter.add(42)
    time.sleep(1)


class MetricsOtelTest:
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
        assert "x" in get_metric_names(tel)

        # Access raw metric data (convert protobuf to dict)
        pbreq = MessageToDict(tel.metric_requests[0].pbreq)
        metric = pbreq["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
        assert metric["name"] == "x"
        assert "sum" in metric
        # Counter should be monotonic
        assert metric["sum"].get("isMonotonic", False) is True
        assert metric["sum"]["aggregationTemporality"] == "AGGREGATION_TEMPORALITY_CUMULATIVE"
        assert metric["sum"]["dataPoints"][0]["asDouble"] == 42.0
