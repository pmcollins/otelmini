from typing import Optional, Sequence

from opentelemetry.sdk.metrics._internal.export import MetricReader
from opentelemetry.sdk.metrics.export import (Metric, MetricExporter, MetricExportResult, MetricsData)
from opentelemetry.metrics import CallbackT, Counter, Histogram, MeterProvider as ApiMeterProvider, ObservableCounter, \
    ObservableGauge, \
    ObservableUpDownCounter, UpDownCounter
from opentelemetry.metrics._internal import Meter as ApiMeter
from opentelemetry.util.types import Attributes


class SimpleMetricExporter(MetricExporter):

    def export(self, metrics: Sequence[Metric], **kwargs) -> MetricExportResult:
        print(metrics)
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        return None


class ExportingMetricReader(MetricReader):

    def __init__(self, exporter: MetricExporter):
        super().__init__()
        self.exporter = exporter

    def _receive_metrics(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000, **kwargs
    ) -> None:
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
        attributes: Optional[Attributes] = None
    ) -> Meter:
        pass


class Meter(ApiMeter):
    def create_counter(self, name: str, unit: str = "", description: str = "") -> Counter:
        pass

    def create_up_down_counter(self, name: str, unit: str = "", description: str = "") -> UpDownCounter:
        pass

    def create_observable_counter(self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "",
                                  description: str = "") -> ObservableCounter:
        pass

    def create_histogram(self, name: str, unit: str = "", description: str = "") -> Histogram:
        pass

    def create_observable_gauge(self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "",
                                description: str = "") -> ObservableGauge:
        pass

    def create_observable_up_down_counter(self, name: str, callbacks: Optional[Sequence[CallbackT]] = None,
                                          unit: str = "", description: str = "") -> ObservableUpDownCounter:
        pass


def main():
    exporter = SimpleMetricExporter()
    reader = ExportingMetricReader(exporter=exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    print(meter_provider.get_meter(name="foo"))
    meter = meter_provider.get_meter("my-meter")
    print(meter)


if __name__ == "__main__":
    main()
