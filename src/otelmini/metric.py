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
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue, InstrumentationScope as PbInstrumentationScope
from opentelemetry.proto.metrics.v1.metrics_pb2 import (
    Metric as PbMetric,
    NumberDataPoint as PbNumberDataPoint,
    ResourceMetrics as PbResourceMetrics,
    ScopeMetrics as PbScopeMetrics,
    Sum as PbSum,
)
from opentelemetry.proto.resource.v1.resource_pb2 import Resource as PbResource

from otelmini._grpclib import GrpcExporter
from otelmini._lib import Exporter
from otelmini.point import AggregationTemporality
from otelmini.point import MetricsData, Metric, ResourceMetrics, ScopeMetrics, Sum, NumberDataPoint
from otelmini.types import Resource, InstrumentationScope

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.metrics import CallbackT
    from opentelemetry.metrics import UpDownCounter as ApiUpDownCounter
    from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
        ExportMetricsServiceRequest,
    )
    from opentelemetry.util.types import Attributes


class MetricExportResult(Enum):
    SUCCESS = 0
    FAILURE = 1


class CounterError(Exception):
    def __init__(self) -> None:
        super().__init__("Counter cannot be decremented (amount must be non-negative)")


class GrpcMetricExporterError(Exception):
    def __init__(self) -> None:
        super().__init__("opentelemetry-proto package is required for GrpcMetricExporter")


class GrpcMetricExporter(Exporter):
    def __init__(self, addr="127.0.0.1:4317", max_retries=3, channel_provider=None, sleep=time.sleep):
        self.addr = addr
        self.max_retries = max_retries
        self.channel_provider = channel_provider
        self.sleep = sleep
        self.exporter = None
        self.init_grpc()

    def init_grpc(self):
        try:
            from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2_grpc import MetricsServiceStub
        except ImportError as err:
            raise GrpcMetricExporterError from err

        if self.exporter:
            return
        self.exporter = GrpcExporter(
            response_class=ExportMetricsServiceResponse,
            addr=self.addr,
            max_retries=self.max_retries,
            channel_provider=self.channel_provider,
            sleep=self.sleep,
            stub_class=MetricsServiceStub,
        )

    def export(self, metrics_data: MetricsData) -> MetricExportResult:
        req = mk_metric_request(metrics_data)
        return self.exporter.export(req)

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return self.exporter.force_flush(timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        self.exporter.shutdown()


def mk_metric_request(metrics_data: MetricsData) -> ExportMetricsServiceRequest:
    resource_metrics_list = []
    for rm in metrics_data.resource_metrics:
        scope_metrics_list = []
        for sm in rm.scope_metrics:
            pb_metrics = []
            for metric in sm.metrics:
                data_points = []
                if isinstance(metric.data, Sum):
                    for point in metric.data.data_points:
                        attributes = [
                            KeyValue(key=k, value=AnyValue(string_value=str(v)))
                            for k, v in point.attributes.items()
                        ]
                        data_points.append(
                            PbNumberDataPoint(
                                attributes=attributes,
                                start_time_unix_nano=point.start_time_unix_nano,
                                time_unix_nano=point.time_unix_nano,
                                as_double=point.value,
                            )
                        )
                    pb_metric_data = PbSum(
                        data_points=data_points,
                        aggregation_temporality=metric.data.aggregation_temporality.value,
                        is_monotonic=metric.data.is_monotonic,
                    )
                    pb_metrics.append(
                        PbMetric(
                            name=metric.name,
                            description=metric.description,
                            unit=metric.unit,
                            sum=pb_metric_data,
                        )
                    )

            scope_metrics_list.append(
                PbScopeMetrics(
                    scope=PbInstrumentationScope(name=sm.scope.name, version=sm.scope.version),
                    metrics=pb_metrics,
                    schema_url=sm.schema_url,
                )
            )

        resource_attributes = [
            KeyValue(key=k, value=AnyValue(string_value=str(v)))
            for k, v in rm.resource.get_attributes().items()
        ]
        resource_metrics_list.append(
            PbResourceMetrics(
                resource=PbResource(attributes=resource_attributes),
                scope_metrics=scope_metrics_list,
                schema_url=rm.schema_url,
            )
        )

    return ExportMetricsServiceRequest(resource_metrics=resource_metrics_list)


class ConsoleMetricExporter(Exporter[Metric]):

    def export(self, metrics: Sequence[Metric]) -> MetricExportResult:
        print(f"exporting metrics: {metrics}")
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        return None


class MetricReader(ABC):

    @abstractmethod
    def set_metric_producer(self, metric_producer):
        pass

    @abstractmethod
    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        pass

    @abstractmethod
    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        pass


class ManualExportingMetricReader(MetricReader):

    def __init__(self, exporter: Exporter[MetricsData]):
        self.metric_producer = None
        self.exporter = exporter

    def set_metric_producer(self, metric_producer):
        self.metric_producer = metric_producer

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        metrics = self.metric_producer.produce()
        self.exporter.export(metrics)
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        pass


class MetricProducer:
    """
    Spec: https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/metrics/sdk.md#metricproducer
    """

    def __init__(self):
        self.counters = []

    def _register_counter(self, counter: Counter) -> None:
        self.counters.append(counter)
        print(f"_register_counter: Counters registered: {len(self.counters)}")

    def produce(self) -> MetricsData:
        print(f"produce: Counters registered: {len(self.counters)}")
        scope = InstrumentationScope(name="opentelemetry")
        data_points = [NumberDataPoint({}, 0, 0, counter.get_value()) for counter in self.counters]
        sum_metric = Sum(
            data_points,
            is_monotonic=True,
            aggregation_temporality=AggregationTemporality.CUMULATIVE
        )
        sm = ScopeMetrics(scope, [Metric("", "", "", sum_metric)], "")
        rm = ResourceMetrics(Resource(), [sm], "")
        return MetricsData([rm])


class MeterProvider(ApiMeterProvider):

    def __init__(self, metric_readers: Sequence[ManualExportingMetricReader] = ()):
        self.metric_producer = MetricProducer()
        self.metric_readers = metric_readers
        for reader in self.metric_readers:
            reader.set_metric_producer(self.metric_producer)

    def get_meter(
        self,
        name: str,
        version: Optional[str] = None,
        schema_url: Optional[str] = None,
        attributes: Optional[Attributes] = None,
    ) -> ApiMeter:
        return Meter(self, name, version, schema_url)

    def _register_counter(self, counter: Counter) -> None:
        self.metric_producer._register_counter(counter)

    def produce_metrics(self):
        return self.metric_producer.produce()


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

    def get_value(self):
        return self._value


class Meter(ApiMeter):

    def __init__(
        self,
        meter_provider: MeterProvider,
        name: str,
        version: Optional[str] = None,
        schema_url: Optional[str] = None,
    ):
        super().__init__(name, version, schema_url)
        self.meter_provider = meter_provider

    def create_counter(self, name: str, unit: str = "", description: str = "") -> ApiCounter:
        counter = Counter(name=name, unit=unit, description=description)
        reg_status = self._register_instrument(name, Counter, unit, description)
        self.meter_provider._register_counter(counter)
        return counter

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
