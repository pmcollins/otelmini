from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

from opentelemetry.metrics import (
    CallbackT,
    Counter,
    Histogram,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.metrics import MeterProvider as ApiMeterProvider
from opentelemetry.metrics._internal import Meter as ApiMeter
from opentelemetry.sdk.metrics._internal.export import MetricReader
from opentelemetry.sdk.metrics.export import Metric, MetricExporter, MetricExportResult, MetricsData

if TYPE_CHECKING:
    from opentelemetry.util.types import Attributes


class SimpleMetricExporter(MetricExporter):
    def export(self, metrics: Sequence[Metric], **kwargs) -> MetricExportResult:  # noqa: ARG002
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:  # noqa: ARG002
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:  # noqa: ARG002
        return None


class ExportingMetricReader(MetricReader):
    def __init__(self, exporter: MetricExporter):
        super().__init__()
        self.exporter = exporter

    def _receive_metrics(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs) -> None:
        pass

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        pass


class MeterProvider(ApiMeterProvider):
    def __init__(self, metric_readers: Sequence[MetricReader] = ()):
        self.metric_readers = metric_readers

    def get_meter(
        self,
        name: str,
        version: Optional[str] = None,
        schema_url: Optional[str] = None,
        attributes: Optional[Attributes] = None,
    ) -> ApiMeter:
        pass


class Meter(ApiMeter):
    def create_counter(self, name: str, unit: str = "", description: str = "") -> Counter:
        pass

    def create_up_down_counter(self, name: str, unit: str = "", description: str = "") -> UpDownCounter:
        pass

    def create_observable_counter(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ObservableCounter:
        pass

    def create_histogram(
        self,
        name: str,
        unit: str = "",
        description: str = "",
        *,
        explicit_bucket_boundaries_advisory: Optional[Sequence[float]] = None,
    ) -> Histogram:
        pass

    def create_observable_gauge(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ObservableGauge:
        pass

    def create_observable_up_down_counter(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ObservableUpDownCounter:
        pass


def main():
    exporter = SimpleMetricExporter()
    reader = ExportingMetricReader(exporter=exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    print(meter_provider.get_meter(name="foo"))  # noqa: T201
    meter = meter_provider.get_meter("my-meter")
    print(meter)  # noqa: T201


if __name__ == "__main__":
    main()
