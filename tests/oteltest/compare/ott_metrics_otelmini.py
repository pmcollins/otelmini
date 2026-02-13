"""Metrics test using otelmini - exports via HTTP/JSON."""

import time
from pathlib import Path
from typing import Sequence

from opentelemetry import metrics

from otelmini.metric import MeterProvider, ManualExportingMetricReader, HttpMetricExporter

from common import (
    COUNTER_NAME,
    COUNTER_UNIT,
    COUNTER_DESCRIPTION,
    COUNTER_VALUE,
    BaseMetricsCompareTest,
)


def create_test_metric():
    """Create a counter and record a value."""
    reader = ManualExportingMetricReader(HttpMetricExporter())
    provider = MeterProvider(metric_readers=(reader,))
    metrics.set_meter_provider(provider)
    meter = metrics.get_meter("compare-test")

    counter = meter.create_counter(
        COUNTER_NAME,
        unit=COUNTER_UNIT,
        description=COUNTER_DESCRIPTION,
    )
    counter.add(COUNTER_VALUE)

    reader.force_flush()
    time.sleep(0.5)


if __name__ == "__main__":
    create_test_metric()


class MetricsOtelminiOtelTest(BaseMetricsCompareTest):
    def requirements(self) -> Sequence[str]:
        # otelmini package (parent of examples dir)
        parent = str(Path(__file__).resolve().parent.parent.parent)
        return (parent,)
