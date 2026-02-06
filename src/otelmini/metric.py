from __future__ import annotations

import atexit
import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from opentelemetry.metrics import Counter as ApiCounter
from opentelemetry.metrics import _Gauge as ApiGauge
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
    GAUGE = "gauge"
    OBSERVABLE_GAUGE = "observable_gauge"


class CounterError(Exception):
    def __init__(self) -> None:
        super().__init__("Counter cannot be decremented (amount must be non-negative)")


def _attributes_to_key(attributes: Optional[Attributes]) -> Tuple[Tuple[str, Any], ...]:
    """Convert attributes dict to a hashable key for aggregation."""
    if not attributes:
        return ()
    return tuple(sorted(attributes.items()))


def _key_to_attributes(key: Tuple[Tuple[str, Any], ...]) -> Dict[str, Any]:
    """Convert hashable key back to attributes dict."""
    return dict(key)


class HttpMetricExporter(Exporter[MetricsData]):
    def __init__(self, endpoint: str = "http://localhost:4318/v1/metrics", timeout: int = 30):
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
    def set_metric_producer(self, metric_producer: MetricProducer) -> None:
        pass

    @abstractmethod
    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        pass

    @abstractmethod
    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        pass


class ManualExportingMetricReader(MetricReader):

    def __init__(self, exporter: Exporter[MetricsData]):
        self.metric_producer: Optional[MetricProducer] = None
        self.exporter = exporter

    def set_metric_producer(self, metric_producer: MetricProducer) -> None:
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
        self.metric_producer: Optional[MetricProducer] = None
        self.exporter = exporter
        self.export_interval_seconds = export_interval_millis / 1000
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        atexit.register(self.shutdown)

    def _run(self) -> None:
        while not self._stop.wait(self.export_interval_seconds):
            self._export()

    def _export(self) -> None:
        if self.metric_producer:
            metrics = self.metric_producer.produce()
            self.exporter.export(metrics)

    def set_metric_producer(self, metric_producer: MetricProducer) -> None:
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

    def __init__(self, resource: Optional[Resource] = None):
        self.resource = resource or create_default_resource()
        self.meters: Dict[str, Dict[InstrumentType, List[Any]]] = {}
        self._start_time_unix_nano = _time_ns()

    def _get_meter_instruments(self, meter_name: str) -> Dict[InstrumentType, List[Any]]:
        if meter_name not in self.meters:
            self.meters[meter_name] = {itype: [] for itype in InstrumentType}
        return self.meters[meter_name]

    def produce(self) -> MetricsData:
        time_unix_nano = _time_ns()
        scope_metrics_list: List[ScopeMetrics] = []

        for meter_name, instruments in self.meters.items():
            metrics = self._produce_metrics_for_meter(instruments, time_unix_nano)
            if metrics:
                scope = InstrumentationScope(name=meter_name)
                scope_metrics_list.append(ScopeMetrics(scope, metrics, ""))

        rm = ResourceMetrics(self.resource, scope_metrics_list, "")
        return MetricsData([rm])

    def _produce_metrics_for_meter(
        self, instruments: Dict[InstrumentType, List[Any]], time_unix_nano: int
    ) -> List[Metric]:
        """Produce metrics from all instruments in a meter."""
        metrics: List[Metric] = []

        for instrument in instruments[InstrumentType.COUNTER]:
            if metric := self._produce_sum_metric(instrument, time_unix_nano, is_monotonic=True):
                metrics.append(metric)

        for instrument in instruments[InstrumentType.UP_DOWN_COUNTER]:
            if metric := self._produce_sum_metric(instrument, time_unix_nano, is_monotonic=False):
                metrics.append(metric)

        for instrument in instruments[InstrumentType.HISTOGRAM]:
            if metric := self._produce_histogram_metric(instrument, time_unix_nano):
                metrics.append(metric)

        for instrument in instruments[InstrumentType.GAUGE]:
            if metric := self._produce_sync_gauge_metric(instrument, time_unix_nano):
                metrics.append(metric)

        for instrument in instruments[InstrumentType.OBSERVABLE_GAUGE]:
            metrics.append(self._produce_observable_gauge_metric(instrument, time_unix_nano))

        return metrics

    def _produce_sum_metric(
        self, instrument: _SumInstrument, time_unix_nano: int, *, is_monotonic: bool
    ) -> Optional[Metric]:
        """Produce a Sum metric from a Counter or UpDownCounter."""
        data_points = [
            NumberDataPoint(
                _key_to_attributes(attr_key),
                self._start_time_unix_nano,
                time_unix_nano,
                value
            )
            for attr_key, value in instrument.get_values().items()
        ]
        if not data_points:
            return None
        sum_data = Sum(
            data_points,
            is_monotonic=is_monotonic,
            aggregation_temporality=AggregationTemporality.CUMULATIVE
        )
        return Metric(instrument.name, instrument.description, instrument.unit, sum_data)

    def _produce_histogram_metric(
        self, instrument: HistogramInstrument, time_unix_nano: int
    ) -> Optional[Metric]:
        """Produce a Histogram metric."""
        data_points = [
            HistogramDataPoint(
                attributes=_key_to_attributes(attr_key),
                start_time_unix_nano=self._start_time_unix_nano,
                time_unix_nano=time_unix_nano,
                count=h_data['count'],
                sum=h_data['sum'],
                bucket_counts=h_data['bucket_counts'],
                explicit_bounds=h_data['explicit_bounds'],
                min=h_data['min'],
                max=h_data['max'],
            )
            for attr_key, h_data in instrument.get_all_histogram_data().items()
        ]
        if not data_points:
            return None
        histogram_data = HistogramData(
            data_points,
            aggregation_temporality=AggregationTemporality.CUMULATIVE
        )
        return Metric(instrument.name, instrument.description, instrument.unit, histogram_data)

    def _produce_sync_gauge_metric(
        self, instrument: GaugeInstrument, time_unix_nano: int
    ) -> Optional[Metric]:
        """Produce a Gauge metric from a sync Gauge instrument."""
        data_points = [
            NumberDataPoint(
                _key_to_attributes(attr_key),
                self._start_time_unix_nano,
                time_unix_nano,
                value
            )
            for attr_key, value in instrument.get_values().items()
        ]
        if not data_points:
            return None
        gauge_data = Gauge(data_points)
        return Metric(instrument.name, instrument.description, instrument.unit, gauge_data)

    def _produce_observable_gauge_metric(
        self, instrument: ObservableGaugeInstrument, time_unix_nano: int
    ) -> Metric:
        """Produce a Gauge metric from an observable Gauge."""
        data_point = NumberDataPoint(
            {}, self._start_time_unix_nano, time_unix_nano, instrument.get_value()
        )
        gauge_data = Gauge([data_point])
        return Metric(instrument.name, instrument.description, instrument.unit, gauge_data)


class MeterProvider(ApiMeterProvider):

    def __init__(
        self,
        metric_readers: Sequence[MetricReader] = (),
        resource: Optional[Resource] = None,
        metric_producer: Optional[MetricProducer] = None,
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

    def _register_instrument(self, instrument: Any, instrument_type: InstrumentType, meter_name: str) -> None:
        """Register an instrument with the metric producer."""
        self.metric_producer._get_meter_instruments(meter_name)[instrument_type].append(instrument)

    def produce_metrics(self) -> MetricsData:
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
        self._values: Dict[Tuple[Tuple[str, Any], ...], float] = {}

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

    def get_values(self) -> Dict[Tuple[Tuple[str, Any], ...], float]:
        """Return all values keyed by attribute tuple."""
        return self._values


class Counter(_SumInstrument, ApiCounter):

    def __init__(self, name: str, unit: str = "", description: str = ""):
        super().__init__(name, unit, description, monotonic=True)


class UpDownCounter(_SumInstrument, ApiUpDownCounter):

    def __init__(self, name: str, unit: str = "", description: str = ""):
        super().__init__(name, unit, description, monotonic=False)


class GaugeInstrument(ApiGauge):
    """Synchronous Gauge instrument - records last value per attribute set."""

    def __init__(self, name: str, unit: str = "", description: str = ""):
        self.name = name
        self.unit = unit
        self.description = description
        self._values: Dict[Tuple[Tuple[str, Any], ...], float] = {}

    def set(
        self,
        amount: float,
        attributes: Optional[Attributes] = None,
        context: Optional[Context] = None,
    ) -> None:
        key = _attributes_to_key(attributes)
        self._values[key] = amount

    def get_values(self) -> Dict[Tuple[Tuple[str, Any], ...], float]:
        """Return all values keyed by attribute tuple."""
        return self._values


class _HistogramAggregation:
    """Aggregation state for a single attribute combination."""

    def __init__(self, boundaries: List[float]):
        self.boundaries = boundaries
        self.bucket_counts: List[int] = [0] * (len(boundaries) + 1)
        self._sum: float = 0.0
        self._count: int = 0
        self._min: float = float('inf')
        self._max: float = float('-inf')

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

    def get_data(self) -> Dict[str, Any]:
        return {
            'count': self._count,
            'sum': self._sum,
            'min': self._min if self._count > 0 else 0.0,
            'max': self._max if self._count > 0 else 0.0,
            'bucket_counts': self.bucket_counts,
            'explicit_bounds': self.boundaries,
        }


class HistogramInstrument(ApiHistogram):
    DEFAULT_BOUNDARIES: List[float] = [0, 5, 10, 25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 7500, 10000]

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
        self.boundaries: List[float] = list(explicit_bucket_boundaries) if explicit_bucket_boundaries else self.DEFAULT_BOUNDARIES
        self._aggregations: Dict[Tuple[Tuple[str, Any], ...], _HistogramAggregation] = {}

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

    def get_all_histogram_data(self) -> Dict[Tuple[Tuple[str, Any], ...], Dict[str, Any]]:
        """Return histogram data for all attribute combinations."""
        return {key: agg.get_data() for key, agg in self._aggregations.items()}


class ObservableGaugeInstrument(ApiObservableGauge):

    def __init__(
        self,
        name: str,
        callbacks: Optional[Sequence[CallbackT]] = None,
        unit: str = "",
        description: str = "",
    ):
        self.name = name
        self.unit = unit
        self.description = description
        self.callbacks: List[CallbackT] = list(callbacks) if callbacks else []

    def get_value(self) -> float:
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
        self.meter_provider._register_instrument(counter, InstrumentType.COUNTER, self._name)
        return counter

    def create_up_down_counter(self, name: str, unit: str = "", description: str = "") -> ApiUpDownCounter:
        up_down_counter = UpDownCounter(name=name, unit=unit, description=description)
        self.meter_provider._register_instrument(up_down_counter, InstrumentType.UP_DOWN_COUNTER, self._name)
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
        self.meter_provider._register_instrument(histogram, InstrumentType.HISTOGRAM, self._name)
        return histogram

    def create_gauge(self, name: str, unit: str = "", description: str = "") -> ApiGauge:
        gauge = GaugeInstrument(name=name, unit=unit, description=description)
        self.meter_provider._register_instrument(gauge, InstrumentType.GAUGE, self._name)
        return gauge

    def create_observable_gauge(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ApiObservableGauge:
        gauge = ObservableGaugeInstrument(
            name=name,
            callbacks=callbacks,
            unit=unit,
            description=description,
        )
        self.meter_provider._register_instrument(gauge, InstrumentType.OBSERVABLE_GAUGE, self._name)
        return gauge

    def create_observable_up_down_counter(
        self, name: str, callbacks: Optional[Sequence[CallbackT]] = None, unit: str = "", description: str = ""
    ) -> ApiObservableUpDownCounter:
        raise NotImplementedError("create_observable_up_down_counter is not yet implemented")
