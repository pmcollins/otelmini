from __future__ import annotations

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

from otelmini._lib import Exporter, ExportResult, _HttpExporter
from otelmini.encode import encode_metrics_request
from otelmini.point import AggregationTemporality
from otelmini.point import MetricsData, Metric, ResourceMetrics, ScopeMetrics, Sum, NumberDataPoint
from otelmini.types import Resource, InstrumentationScope

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.metrics import CallbackT
    from opentelemetry.metrics import UpDownCounter as ApiUpDownCounter
    from opentelemetry.util.types import Attributes


class MetricExportResult(Enum):
    SUCCESS = 0
    FAILURE = 1


class CounterError(Exception):
    def __init__(self) -> None:
        super().__init__("Counter cannot be decremented (amount must be non-negative)")


class HttpMetricExporter(Exporter[MetricsData]):
    def __init__(self, endpoint="http://localhost:4318/v1/metrics", timeout=30):
        self._exporter = _HttpExporter(endpoint, timeout)

    def export(self, metrics_data: MetricsData) -> ExportResult:
        data = encode_metrics_request(metrics_data)
        return self._exporter.export(data)

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        pass


class ConsoleMetricExporter(Exporter[MetricsData]):
    def export(self, items: MetricsData) -> ExportResult:
        print(encode_metrics_request(items))  # noqa: T201
        return ExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        pass


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

    def produce(self) -> MetricsData:
        scope = InstrumentationScope(name="opentelemetry")
        metrics = []
        for counter in self.counters:
            data_point = NumberDataPoint({}, 0, 0, counter.get_value())
            sum_metric = Sum(
                [data_point],
                is_monotonic=True,
                aggregation_temporality=AggregationTemporality.CUMULATIVE
            )
            metrics.append(Metric(counter.name, counter.description, counter.unit, sum_metric))
        sm = ScopeMetrics(scope, metrics, "")
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
