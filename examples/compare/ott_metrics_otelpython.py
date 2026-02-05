"""Metrics test using opentelemetry-python SDK - exports via HTTP/protobuf."""

import time
from pathlib import Path
from typing import Sequence

from common import (
    COUNTER_NAME,
    COUNTER_UNIT,
    COUNTER_DESCRIPTION,
    COUNTER_VALUE,
    BaseMetricsCompareTest,
)


def create_test_metric():
    """Create a counter and record a value."""
    # Import SDK here since it's installed by oteltest
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

    exporter = OTLPMetricExporter()
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=1000)
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    meter = metrics.get_meter("compare-test")

    counter = meter.create_counter(
        COUNTER_NAME,
        unit=COUNTER_UNIT,
        description=COUNTER_DESCRIPTION,
    )
    counter.add(COUNTER_VALUE)

    time.sleep(2)
    provider.shutdown()


if __name__ == "__main__":
    create_test_metric()


class MetricsOtelpythonOtelTest(BaseMetricsCompareTest):
    def requirements(self) -> Sequence[str]:
        return (
            "opentelemetry-sdk",
            "opentelemetry-exporter-otlp-proto-http",
        )
