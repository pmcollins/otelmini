"""
Test that PeriodicExportingMetricReader exports at the configured interval.
Creates a counter and adds to it over ~5 seconds with export_interval_millis=1500,
so we expect multiple periodic exports.
"""

import time
from typing import Mapping, Optional, Sequence

from opentelemetry import metrics

from _lib import package
from otelmini.metric import (
    HttpMetricExporter,
    MeterProvider,
    PeriodicExportingMetricReader,
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

        # Should have multiple metric exports (interval triggered + shutdown)
        # With ~5s total time and 1.5s interval, we expect 3-4 exports
        num_exports = len(tel.metric_requests)
        assert num_exports >= 3, f"expected at least 3 exports, got {num_exports}"

        # Each export should have our counter metric
        for i, req in enumerate(tel.metric_requests):
            pbreq = MessageToDict(req.pbreq)
            metric = pbreq["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]
            assert metric["name"] == "requests", f"export {i}: expected 'requests' metric"


if __name__ == "__main__":
    reader = PeriodicExportingMetricReader(
        HttpMetricExporter(),
        export_interval_millis=1500,  # 1.5 second interval
    )
    provider = MeterProvider(metric_readers=(reader,))
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter("test-meter")
    counter = meter.create_counter("requests")

    # Add to counter over ~5 seconds
    for i in range(10):
        counter.add(1)
        time.sleep(0.5)

    provider.shutdown()
