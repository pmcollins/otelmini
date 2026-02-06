from __future__ import annotations

import atexit
import threading
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
from opentelemetry.metrics import UpDownCounter as ApiUpDownCounter

from otelmini._lib import Exporter, ExportResult, _HttpExporter
from otelmini.encode import encode_metrics_request
from otelmini.point import AggregationTemporality
from otelmini.point import MetricsData, Metric, ResourceMetrics, ScopeMetrics, Sum, NumberDataPoint
from otelmini.point import Histogram as HistogramData, HistogramDataPoint, Gauge
from otelmini.resource import create_default_resource
from otelmini.types import Resource, InstrumentationScope, _time_ns

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.metrics import CallbackT
    from opentelemetry.util.types import Attributes


class InstrumentType(Enum):
    """Types of metric instruments."""
    COUNTER = "counter"
    UP_DOWN_COUNTER = "up_down_counter"
    HISTOGRAM = "histogram"
    OBSERVABLE_GAUGE = "observable_gauge"


class CounterError(Exception):
    def __init__(self) -> None:
        super().__init__("Counter cannot be decremented (amount must be non-negative)")


def _attributes_to_key(attributes: Optional[Attributes]) -> tuple:
    """Convert attributes dict to a hashable key for aggregation."""
    if not attributes:
        return ()
    return tuple(sorted(attributes.items()))


def _key_to_attributes(key: tuple) -> dict:
    """Convert hashable key back to attributes dict."""
    return dict(key)


class HttpMetricExporter(Exporter[MetricsData]):
    def __init__(self, endpoint="http://localhost:4318/v1/metrics", timeout=30):
        self._exporter = _HttpExporter(endpoint, timeout)

    def export(self, metrics_data: MetricsData) -> ExportResult:
        data = encode_metrics_request(metrics_data)
        return self._exporter.export(data)


class ConsoleMetricExporter(Exporter[MetricsData]):
    def export(self, items: MetricsData) -> ExportResult:
        print(encode_metrics_request(items))  # noqa: T201
        return ExportResult.SUCCESS


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


class PeriodicExportingMetricReader(MetricReader):
    """Periodically exports metrics at a configurable interval."""

    def __init__(
        self,
        exporter: Exporter[MetricsData],
        export_interval_millis: float = 60_000,
    ):
        self.metric_producer = None
        self.exporter = exporter
        self.export_interval_seconds = export_interval_millis / 1000
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        atexit.register(self.shutdown)

    def _run(self):
        while not self._stop.wait(self.export_interval_seconds):
            self._export()

    def _export(self):
        if self.metric_producer:
            metrics = self.metric_producer.produce()
            self.exporter.export(metrics)

    def set_metric_producer(self, metric_producer):
        self.metric_producer = metric_producer

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        self._export()
        return True

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        self._stop.set()
        self._export()  # Final export
        self._thread.join(timeout=timeout_millis / 1000)


class MetricProducer:
    """
    Spec: https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/metrics/sdk.md#metricproducer
    """

    def __init__(self, resource: Resource = None):
        self.resource = resource or create_default_resource()
        self.meters = {}  # meter_name -> {InstrumentType -> list of instruments}
        self._start_time_unix_nano = _time_ns()

    def _get_meter_instruments(self, meter_name: str) -> dict:
        if meter_name not in self.meters:
            self.meters[meter_name] = {itype: [] for itype in InstrumentType}
        return self.meters[meter_name]

    def _register_counter(self, counter: Counter, meter_name: str) -> None:
        self._get_meter_instruments(meter_name)[InstrumentType.COUNTER].append(counter)

    def _register_up_down_counter(self, up_down_counter: UpDownCounter, meter_name: str) -> None:
        self._get_meter_instruments(meter_name)[InstrumentType.UP_DOWN_COUNTER].append(up_down_counter)

    def _register_histogram(self, histogram: HistogramInstrument, meter_name: str) -> None:
        self._get_meter_instruments(meter_name)[InstrumentType.HISTOGRAM].append(histogram)

    def _register_observable_gauge(self, gauge: ObservableGaugeInstrument, meter_name: str) -> None:
        self._get_meter_instruments(meter_name)[InstrumentType.OBSERVABLE_GAUGE].append(gauge)

    def produce(self) -> MetricsData:
        time_unix_nano = _time_ns()
        scope_metrics_list = []

        for meter_name, instruments in self.meters.items():
            scope = InstrumentationScope(name=meter_name)
            metrics = []
            for counter in instruments[InstrumentType.COUNTER]:
                data_points = []
                for attr_key, value in counter.get_values().items():
                    data_points.append(NumberDataPoint(
                        _key_to_attributes(attr_key),
                        self._start_time_unix_nano,
                        time_unix_nano,
                        value
                    ))
                if data_points:
                    sum_metric = Sum(
                        data_points,
                        is_monotonic=True,
                        aggregation_temporality=AggregationTemporality.CUMULATIVE
                    )
                    metrics.append(Metric(counter.name, counter.description, counter.unit, sum_metric))
            for up_down_counter in instruments[InstrumentType.UP_DOWN_COUNTER]:
                data_points = []
                for attr_key, value in up_down_counter.get_values().items():
                    data_points.append(NumberDataPoint(
                        _key_to_attributes(attr_key),
                        self._start_time_unix_nano,
                        time_unix_nano,
                        value
                    ))
                if data_points:
                    sum_metric = Sum(
                        data_points,
                        is_monotonic=False,
                        aggregation_temporality=AggregationTemporality.CUMULATIVE
                    )
                    metrics.append(Metric(up_down_counter.name, up_down_counter.description, up_down_counter.unit, sum_metric))
            for histogram in instruments[InstrumentType.HISTOGRAM]:
                data_points = []
                for attr_key, h_data in histogram.get_all_histogram_data().items():
                    data_points.append(HistogramDataPoint(
                        attributes=_key_to_attributes(attr_key),
                        start_time_unix_nano=self._start_time_unix_nano,
                        time_unix_nano=time_unix_nano,
                        count=h_data['count'],
                        sum=h_data['sum'],
                        bucket_counts=h_data['bucket_counts'],
                        explicit_bounds=h_data['explicit_bounds'],
                        min=h_data['min'],
                        max=h_data['max'],
                    ))
                if data_points:
                    histogram_metric = HistogramData(
                        data_points,
                        aggregation_temporality=AggregationTemporality.CUMULATIVE
                    )
                    metrics.append(Metric(histogram.name, histogram.description, histogram.unit, histogram_metric))
            for gauge in instruments[InstrumentType.OBSERVABLE_GAUGE]:
                data_point = NumberDataPoint(
                    {}, self._start_time_unix_nano, time_unix_nano, gauge.get_value()
                )
                gauge_metric = Gauge([data_point])
                metrics.append(Metric(gauge.name, gauge.description, gauge.unit, gauge_metric))
            if metrics:
                scope_metrics_list.append(ScopeMetrics(scope, metrics, ""))

        rm = ResourceMetrics(self.resource, scope_metrics_list, "")
        return MetricsData([rm])


class MeterProvider(ApiMeterProvider):

    def __init__(
        self,
        metric_readers: Sequence[MetricReader] = (),
        resource: Resource = None,
        metric_producer: MetricProducer = None,
    ):
        self.metric_producer = metric_producer or MetricProducer(resource=resource)
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

    def _register_counter(self, counter: Counter, meter_name: str) -> None:
        self.metric_producer._register_counter(counter, meter_name)

    def _register_up_down_counter(self, up_down_counter: UpDownCounter, meter_name: str) -> None:
        self.metric_producer._register_up_down_counter(up_down_counter, meter_name)

    def _register_histogram(self, histogram: HistogramInstrument, meter_name: str) -> None:
        self.metric_producer._register_histogram(histogram, meter_name)

    def _register_observable_gauge(self, gauge: ObservableGaugeInstrument, meter_name: str) -> None:
        self.metric_producer._register_observable_gauge(gauge, meter_name)

    def produce_metrics(self):
        return self.metric_producer.produce()

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        for reader in self.metric_readers:
            reader.shutdown(timeout_millis)


class _SumInstrument:
    """Base class for Counter and UpDownCounter instruments."""

    def __init__(self, name: str, unit: str = "", description: str = "", *, monotonic: bool = False):
        self.name = name
        self.unit = unit
        self.description = description
        self._monotonic = monotonic
        self._values: dict[tuple, float] = {}  # attribute_key -> value

    def add(
        self,
        amount: float,
        attributes: Optional[Attributes] = None,
        context: Optional[Context] = None,
    ) -> None:
        if self._monotonic and amount < 0:
            raise CounterError
        key = _attributes_to_key(attributes)
        self._values[key] = self._values.get(key, 0.0) + amount

    def get_values(self) -> dict[tuple, float]:
        """Return all values keyed by attribute tuple."""
        return self._values


class Counter(_SumInstrument, ApiCounter):

    def __init__(self, name: str, unit: str = "", description: str = ""):
        super().__init__(name, unit, description, monotonic=True)


class UpDownCounter(_SumInstrument, ApiUpDownCounter):

    def __init__(self, name: str, unit: str = "", description: str = ""):
        super().__init__(name, unit, description, monotonic=False)


class _HistogramAggregation:
    """Aggregation state for a single attribute combination."""

    def __init__(self, boundaries: list):
        self.boundaries = boundaries
        self.bucket_counts = [0] * (len(boundaries) + 1)
        self._sum = 0.0
        self._count = 0
        self._min = float('inf')
        self._max = float('-inf')

    def record(self, amount: float) -> None:
        self._sum += amount
        self._count += 1
        self._min = min(self._min, amount)
        self._max = max(self._max, amount)
        for i, bound in enumerate(self.boundaries):
            if amount < bound:
                self.bucket_counts[i] += 1
                return
        self.bucket_counts[-1] += 1

    def get_data(self) -> dict:
        return {
            'count': self._count,
            'sum': self._sum,
            'min': self._min if self._count > 0 else 0.0,
            'max': self._max if self._count > 0 else 0.0,
            'bucket_counts': self.bucket_counts,
            'explicit_bounds': self.boundaries,
        }


class HistogramInstrument(ApiHistogram):
    DEFAULT_BOUNDARIES = [0, 5, 10, 25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 7500, 10000]

    def __init__(
        self,
        name: str,
        unit: str = "",
        description: str = "",
        explicit_bucket_boundaries: Optional[Sequence[float]] = None,
    ):
        self.name = name
        self.unit = unit
        self.description = description
        self.boundaries = list(explicit_bucket_boundaries) if explicit_bucket_boundaries else self.DEFAULT_BOUNDARIES
        self._aggregations: dict[tuple, _HistogramAggregation] = {}  # attribute_key -> aggregation

    def record(
        self,
        amount: float,
        attributes: Optional[Attributes] = None,
        context: Optional[Context] = None,
    ) -> None:
        key = _attributes_to_key(attributes)
        if key not in self._aggregations:
            self._aggregations[key] = _HistogramAggregation(self.boundaries)
        self._aggregations[key].record(amount)

    def get_all_histogram_data(self) -> dict[tuple, dict]:
        """Return histogram data for all attribute combinations."""
        return {key: agg.get_data() for key, agg in self._aggregations.items()}


class ObservableGaugeInstrument(ApiObservableGauge):

    def __init__(
        self,
        name: str,
        callbacks: Optional[Sequence] = None,
        unit: str = "",
        description: str = "",
    ):
        self.name = name
        self.unit = unit
        self.description = description
        self.callbacks = list(callbacks) if callbacks else []

    def get_value(self):
        # Invoke callbacks, return latest observation value
        for callback in self.callbacks:
            for obs in callback():
                return obs.value  # Simplified: first observation
        return 0.0


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
        self._name = name

    def create_counter(self, name: str, unit: str = "", description: str = "") -> ApiCounter:
        counter = Counter(name=name, unit=unit, description=description)
        self._register_instrument(name, Counter, unit, description)
        self.meter_provider._register_counter(counter, self._name)
        return counter

    def create_up_down_counter(self, name: str, unit: str = "", description: str = "") -> ApiUpDownCounter:
        up_down_counter = UpDownCounter(name=name, unit=unit, description=description)
        self._register_instrument(name, UpDownCounter, unit, description)
        self.meter_provider._register_up_down_counter(up_down_counter, self._name)
        return up_down_counter

    def create_observable_counter(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ApiObservableCounter:
        raise NotImplementedError("create_observable_counter is not yet implemented")

    def create_histogram(
        self,
        name: str,
        unit: str = "",
        description: str = "",
        *,
        explicit_bucket_boundaries_advisory: Optional[Sequence[float]] = None,
    ) -> ApiHistogram:
        histogram = HistogramInstrument(
            name=name,
            unit=unit,
            description=description,
            explicit_bucket_boundaries=explicit_bucket_boundaries_advisory,
        )
        self._register_instrument(name, HistogramInstrument, unit, description)
        self.meter_provider._register_histogram(histogram, self._name)
        return histogram

    def create_observable_gauge(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ApiObservableGauge:
        gauge = ObservableGaugeInstrument(
            name=name,
            callbacks=callbacks,
            unit=unit,
            description=description,
        )
        self._register_instrument(name, ObservableGaugeInstrument, unit, description)
        self.meter_provider._register_observable_gauge(gauge, self._name)
        return gauge

    def create_observable_up_down_counter(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ApiObservableUpDownCounter:
        raise NotImplementedError("create_observable_up_down_counter is not yet implemented")
