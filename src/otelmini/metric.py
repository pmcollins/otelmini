from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Optional, Sequence

from opentelemetry.metrics import Counter as ApiCounter
from opentelemetry.metrics import Histogram as ApiHistogram
from opentelemetry.metrics import Meter as ApiMeter
from opentelemetry.metrics import MeterProvider as ApiMeterProvider
from opentelemetry.metrics import ObservableCounter as ApiObservableCounter
from opentelemetry.metrics import ObservableGauge as ApiObservableGauge
from opentelemetry.metrics import ObservableUpDownCounter as ApiObservableUpDownCounter

from otelmini._grpclib import GrpcExporter

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.metrics import CallbackT
    from opentelemetry.metrics import UpDownCounter as ApiUpDownCounter
    from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
        ExportMetricsServiceRequest,
    )
    from opentelemetry.util.types import Attributes


class MetricExporter(ABC):
    @abstractmethod
    def export(self, metrics: Sequence[Metric]) -> MetricExportResult:
        pass

    @abstractmethod
    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        pass

    @abstractmethod
    def shutdown(self, timeout_millis: float = 30_000) -> None:
        pass


class MetricExportResult(Enum):
    SUCCESS = 0
    FAILURE = 1


class Metric:
    pass


class MetricReader(ABC):
    @abstractmethod
    def _receive_metrics(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs) -> None:
        pass

    @abstractmethod
    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        pass


class MetricsData:
    pass


def mk_metric_request(metrics: Sequence[Metric]) -> ExportMetricsServiceRequest:  # noqa: ARG001
    from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
    from opentelemetry.proto.metrics.v1.metrics_pb2 import ResourceMetrics

    return ExportMetricsServiceRequest(resource_metrics=[ResourceMetrics()])


class CounterError(Exception):
    def __init__(self) -> None:
        super().__init__("Counter cannot be decremented (amount must be non-negative)")


class MetricResponseError(Exception):
    def __init__(self, rejected_data_points: int, error_message: str) -> None:
        super().__init__(
            f"partial success: rejected_data_points: [{rejected_data_points}], error_message: [{error_message}]"
        )


class GrpcMetricExporterError(Exception):
    def __init__(self) -> None:
        super().__init__("opentelemetry-proto package is required for GrpcMetricExporter")


def handle_metric_response(resp):
    if resp.HasField("partial_success") and resp.partial_success:
        ps = resp.partial_success
        import logging

        logging.warning(str(MetricResponseError(ps.rejected_data_points, ps.error_message)))


class GrpcMetricExporter(MetricExporter):
    def __init__(self, addr="127.0.0.1:4317", max_retries=3, channel_provider=None, sleep=time.sleep):
        try:
            from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2_grpc import MetricsServiceStub
        except ImportError as err:
            raise GrpcMetricExporterError from err

        self._exporter = GrpcExporter(
            addr=addr,
            max_retries=max_retries,
            channel_provider=channel_provider,
            sleep=sleep,
            stub_class=MetricsServiceStub,
            response_handler=handle_metric_response,
        )

    def export(self, metrics: Sequence[Metric]) -> MetricExportResult:
        req = mk_metric_request(metrics)
        return self._exporter.export_request(req)

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return self._exporter.force_flush(timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        self._exporter.shutdown()


class SimpleMetricExporter(MetricExporter):
    def export(self, metrics: Sequence[Metric]) -> MetricExportResult:
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000) -> None:
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
        return Meter(name, version, schema_url, self.metric_readers)


class Counter(ApiCounter):
    def __init__(self, name: str, unit: str = "", description: str = ""):
        self.name = name
        self.unit = unit
        self.description = description
        self._value = 0.0

    def add(
        self,
        amount: float,
        attributes: Optional[Attributes] = None,
        context: Optional[Context] = None,
    ) -> None:
        if amount < 0:
            raise CounterError
        self._value += amount


class Meter(ApiMeter):
    def __init__(
        self,
        name: str,
        version: Optional[str] = None,
        schema_url: Optional[str] = None,
        metric_readers: Sequence[MetricReader] = (),
    ):
        super().__init__(name, version, schema_url)
        self.metric_readers = metric_readers

    def create_counter(self, name: str, unit: str = "", description: str = "") -> ApiCounter:
        return Counter(name=name, unit=unit, description=description)

    def create_up_down_counter(self, name: str, unit: str = "", description: str = "") -> ApiUpDownCounter:
        pass

    def create_observable_counter(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ApiObservableCounter:
        pass

    def create_histogram(
        self,
        name: str,
        unit: str = "",
        description: str = "",
        *,
        explicit_bucket_boundaries_advisory: Optional[Sequence[float]] = None,
    ) -> ApiHistogram:
        pass

    def create_observable_gauge(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ApiObservableGauge:
        pass

    def create_observable_up_down_counter(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ApiObservableUpDownCounter:
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
