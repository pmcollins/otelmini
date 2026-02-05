"""
API-only Histogram test using auto-instrumentation.
This script only imports from opentelemetry.* - no otelmini imports.
"""

import time
from typing import Mapping, Optional, Sequence

from opentelemetry import metrics

from _lib import package


if __name__ == '__main__':
    meter = metrics.get_meter("my-meter")
    histogram = meter.create_histogram(
        "request_latency",
        unit="ms",
        description="Request latency in milliseconds"
    )
    # Record latency-like values
    histogram.record(1)
    histogram.record(5)
    histogram.record(10)
    histogram.record(50)
    histogram.record(100)
    histogram.record(500)
    time.sleep(1)


class HistogramOtelTest:
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
        assert "request_latency" in get_metric_names(tel)

        # Access raw metric data (convert protobuf to dict)
        pbreq = MessageToDict(tel.metric_requests[0].pbreq)
        metric = pbreq["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
        assert metric["name"] == "request_latency"
        assert metric["unit"] == "ms"
        assert metric["description"] == "Request latency in milliseconds"
        assert "histogram" in metric

        histogram = metric["histogram"]
        assert histogram["aggregationTemporality"] == "AGGREGATION_TEMPORALITY_CUMULATIVE"

        dp = histogram["dataPoints"][0]
        assert int(dp["count"]) == 6  # 6 recorded values
        assert dp["sum"] == 666.0  # 1 + 5 + 10 + 50 + 100 + 500
        assert dp["min"] == 1.0
        assert dp["max"] == 500.0
        assert "bucketCounts" in dp
        assert "explicitBounds" in dp
