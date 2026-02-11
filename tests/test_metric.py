import json
from typing import Sequence

from otelmini.export import Exporter, T, ExportResult
from otelmini.metric import ManualExportingMetricReader, MeterProvider, PeriodicExportingMetricReader
from otelmini.encode import encode_metrics_request
from otelmini.point import (
    AggregationTemporality,
    Metric,
    MetricsData,
    NumberDataPoint,
    ResourceMetrics,
    ScopeMetrics,
    Sum,
)
from otelmini.types import InstrumentationScope, Resource


def test_encode_metrics_request():
    data_point = NumberDataPoint(
        attributes={"label": "value"},
        start_time_unix_nano=1678886400000000000,
        time_unix_nano=1678886401000000000,
        value=123.45,
    )
    sum_data = Sum(
        data_points=[data_point],
        aggregation_temporality=AggregationTemporality.CUMULATIVE,
        is_monotonic=True,
    )
    metric = Metric(
        name="test.metric",
        description="A test metric",
        unit="ms",
        data=sum_data,
    )
    scope = InstrumentationScope(name="test.scope", version="0.1.0")
    scope_metrics = ScopeMetrics(
        scope=scope,
        metrics=[metric],
        schema_url="http://example.com/schema",
    )
    resource = Resource()
    resource.get_attributes().update({"service.name": "test_service"})
    resource_metrics = ResourceMetrics(
        resource=resource,
        scope_metrics=[scope_metrics],
        schema_url="http://example.com/resource_schema",
    )
    metrics_data = MetricsData(resource_metrics=[resource_metrics])

    encoded_json = encode_metrics_request(metrics_data)
    decoded = json.loads(encoded_json)

    assert "resourceMetrics" in decoded
    assert len(decoded["resourceMetrics"]) == 1

    rm = decoded["resourceMetrics"][0]
    assert rm["schemaUrl"] == "http://example.com/resource_schema"
    assert len(rm["resource"]["attributes"]) == 1
    assert rm["resource"]["attributes"][0]["key"] == "service.name"
    assert rm["resource"]["attributes"][0]["value"]["stringValue"] == "test_service"

    assert len(rm["scopeMetrics"]) == 1
    sm = rm["scopeMetrics"][0]
    assert sm["schemaUrl"] == "http://example.com/schema"
    assert sm["scope"]["name"] == "test.scope"
    assert sm["scope"]["version"] == "0.1.0"

    assert len(sm["metrics"]) == 1
    m = sm["metrics"][0]
    assert m["name"] == "test.metric"
    assert m["description"] == "A test metric"
    assert m["unit"] == "ms"

    s = m["sum"]
    assert s["isMonotonic"] is True
    assert s["aggregationTemporality"] == AggregationTemporality.CUMULATIVE.value

    assert len(s["dataPoints"]) == 1
    dp = s["dataPoints"][0]
    assert dp["startTimeUnixNano"] == "1678886400000000000"
    assert dp["timeUnixNano"] == "1678886401000000000"
    assert dp["asDouble"] == 123.45
    assert len(dp["attributes"]) == 1
    assert dp["attributes"][0]["key"] == "label"
    assert dp["attributes"][0]["value"]["stringValue"] == "value"


def test_metric():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_counter(name="x")
    counter.add(42)
    reader.force_flush()
    assert len(exporter.get_exports())


def test_metric_name_and_metadata():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_counter(name="requests", unit="1", description="Number of requests")
    counter.add(10)
    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.name == "requests"
    assert metric.unit == "1"
    assert metric.description == "Number of requests"
    assert metric.data.data_points[0].value == 10


class FakeExporter(Exporter):
    def __init__(self):
        self.exports = []

    def export(self, items: Sequence[T]) -> ExportResult:
        self.exports.append(items)
        return ExportResult.SUCCESS

    def get_exports(self):
        return self.exports


# Attribute Aggregation Tests

def test_counter_with_attributes():
    """Test that counter aggregates by attribute combination."""
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_counter(name="requests")

    counter.add(1, {"method": "GET"})
    counter.add(2, {"method": "POST"})
    counter.add(3, {"method": "GET"})

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    data_points = {
        tuple(sorted(dp.attributes.items())): dp.value
        for dp in metric.data.data_points
    }

    assert len(data_points) == 2
    assert data_points[(("method", "GET"),)] == 4  # 1 + 3
    assert data_points[(("method", "POST"),)] == 2


def test_counter_no_attributes_separate_from_with_attributes():
    """Test that no-attribute calls aggregate separately."""
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_counter(name="requests")

    counter.add(10)  # No attributes
    counter.add(5, {"region": "us"})
    counter.add(3)  # No attributes

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    data_points = {
        tuple(sorted(dp.attributes.items())): dp.value
        for dp in metric.data.data_points
    }

    assert len(data_points) == 2
    assert data_points[()] == 13  # 10 + 3
    assert data_points[(("region", "us"),)] == 5


def test_histogram_with_attributes():
    """Test that histogram aggregates by attribute combination."""
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    histogram = meter.create_histogram(
        name="latency",
        explicit_bucket_boundaries_advisory=[10, 100]
    )

    histogram.record(5, {"endpoint": "/api"})
    histogram.record(50, {"endpoint": "/api"})
    histogram.record(200, {"endpoint": "/health"})

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    data_points = {
        tuple(sorted(dp.attributes.items())): dp
        for dp in metric.data.data_points
    }

    assert len(data_points) == 2

    api_dp = data_points[(("endpoint", "/api"),)]
    assert api_dp.count == 2
    assert api_dp.sum == 55
    assert api_dp.min == 5
    assert api_dp.max == 50

    health_dp = data_points[(("endpoint", "/health"),)]
    assert health_dp.count == 1
    assert health_dp.sum == 200


# UpDownCounter Tests

def test_up_down_counter_increment_decrement():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    up_down_counter = meter.create_up_down_counter(name="connections")

    up_down_counter.add(10)
    up_down_counter.add(-3)
    up_down_counter.add(5)
    up_down_counter.add(-7)

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.data.data_points[0].value == 5  # 10 - 3 + 5 - 7 = 5


def test_up_down_counter_metadata():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    up_down_counter = meter.create_up_down_counter(
        name="active_connections",
        unit="1",
        description="Number of active connections"
    )
    up_down_counter.add(42)
    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.name == "active_connections"
    assert metric.unit == "1"
    assert metric.description == "Number of active connections"


def test_up_down_counter_is_non_monotonic():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    up_down_counter = meter.create_up_down_counter(name="items")
    up_down_counter.add(10)
    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.data.is_monotonic is False


# Histogram Tests

def test_histogram_basic_recording():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    histogram = meter.create_histogram(name="request_latency", unit="ms", description="Request latency")

    histogram.record(10)
    histogram.record(20)
    histogram.record(30)

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    data_point = metric.data.data_points[0]

    assert data_point.count == 3
    assert data_point.sum == 60
    assert data_point.min == 10
    assert data_point.max == 30


def test_histogram_bucket_distribution():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    histogram = meter.create_histogram(
        name="latency",
        explicit_bucket_boundaries_advisory=[10, 50, 100]
    )

    # Values: <10 bucket, <50 bucket, <100 bucket, >=100 bucket
    histogram.record(5)   # bucket 0: <10
    histogram.record(15)  # bucket 1: <50
    histogram.record(25)  # bucket 1: <50
    histogram.record(75)  # bucket 2: <100
    histogram.record(150) # bucket 3: >=100

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    data_point = metric.data.data_points[0]

    assert data_point.bucket_counts == [1, 2, 1, 1]  # [<10, <50, <100, >=100]


def test_histogram_custom_boundaries():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    custom_boundaries = [1, 5, 10]
    histogram = meter.create_histogram(
        name="custom_histogram",
        explicit_bucket_boundaries_advisory=custom_boundaries
    )

    # Must record at least one value to produce a data point
    histogram.record(3)
    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    data_point = metric.data.data_points[0]

    assert list(data_point.explicit_bounds) == [1, 5, 10]


# ObservableGauge Tests

def test_observable_gauge_callback_invoked():
    callback_invoked = []

    def my_callback(options):
        callback_invoked.append(True)
        from opentelemetry.metrics import Observation
        return [Observation(value=42.0)]

    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    gauge = meter.create_observable_gauge(
        name="cpu_usage",
        callbacks=[my_callback]
    )

    reader.force_flush()

    assert len(callback_invoked) == 1


def test_observable_gauge_value_captured():
    def my_callback(options):
        from opentelemetry.metrics import Observation
        return [Observation(value=75.5)]

    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    gauge = meter.create_observable_gauge(
        name="memory_usage",
        callbacks=[my_callback],
        unit="%",
        description="Memory usage percentage"
    )

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]

    assert metric.name == "memory_usage"
    assert metric.unit == "%"
    assert metric.description == "Memory usage percentage"
    assert metric.data.data_points[0].value == 75.5


def test_observable_gauge_no_callback():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    gauge = meter.create_observable_gauge(name="empty_gauge")

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.data.data_points[0].value == 0.0


# ObservableCounter Tests

def test_observable_counter_callback_invoked():
    callback_invoked = []

    def my_callback(options):
        callback_invoked.append(True)
        from opentelemetry.metrics import Observation
        return [Observation(value=1000)]

    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_observable_counter(
        name="requests_total",
        callbacks=[my_callback]
    )

    reader.force_flush()

    assert len(callback_invoked) == 1


def test_observable_counter_value_captured():
    def my_callback(options):
        from opentelemetry.metrics import Observation
        return [Observation(value=5000)]

    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_observable_counter(
        name="bytes_received",
        callbacks=[my_callback],
        unit="By",
        description="Total bytes received"
    )

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]

    assert metric.name == "bytes_received"
    assert metric.unit == "By"
    assert metric.description == "Total bytes received"
    assert metric.data.data_points[0].value == 5000
    # ObservableCounter produces a Sum that is monotonic and cumulative
    assert metric.data.is_monotonic is True


# ObservableUpDownCounter Tests

def test_observable_up_down_counter_callback_invoked():
    callback_invoked = []

    def my_callback(options):
        callback_invoked.append(True)
        from opentelemetry.metrics import Observation
        return [Observation(value=50)]

    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_observable_up_down_counter(
        name="active_connections",
        callbacks=[my_callback]
    )

    reader.force_flush()

    assert len(callback_invoked) == 1


def test_observable_up_down_counter_value_captured():
    def my_callback(options):
        from opentelemetry.metrics import Observation
        return [Observation(value=-10)]  # Can be negative

    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_observable_up_down_counter(
        name="queue_depth",
        callbacks=[my_callback],
        unit="1",
        description="Current queue depth"
    )

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]

    assert metric.name == "queue_depth"
    assert metric.unit == "1"
    assert metric.description == "Current queue depth"
    assert metric.data.data_points[0].value == -10
    # ObservableUpDownCounter produces a Sum that is NOT monotonic
    assert metric.data.is_monotonic is False


# Sync Gauge Tests

def test_sync_gauge_set_value():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    gauge = meter.create_gauge(name="temperature", unit="C", description="Current temperature")

    gauge.set(25.5)

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]

    assert metric.name == "temperature"
    assert metric.unit == "C"
    assert metric.description == "Current temperature"
    assert metric.data.data_points[0].value == 25.5


def test_sync_gauge_overwrites_previous_value():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    gauge = meter.create_gauge(name="queue_size")

    gauge.set(10)
    gauge.set(20)
    gauge.set(15)  # Last value wins

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.data.data_points[0].value == 15


def test_sync_gauge_with_attributes():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    gauge = meter.create_gauge(name="cpu_temp")

    gauge.set(65.0, {"core": "0"})
    gauge.set(70.0, {"core": "1"})
    gauge.set(68.0, {"core": "0"})  # Overwrites core 0's value

    reader.force_flush()

    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    data_points = {
        tuple(sorted(dp.attributes.items())): dp
        for dp in metric.data.data_points
    }

    assert len(data_points) == 2
    assert data_points[(("core", "0"),)].value == 68.0
    assert data_points[(("core", "1"),)].value == 70.0


# PeriodicExportingMetricReader Tests

def test_periodic_reader_exports_on_shutdown():
    import time
    exporter = FakeExporter()
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60_000)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_counter(name="test_counter")
    counter.add(100)

    # Shutdown should trigger final export
    meter_provider.shutdown()

    assert len(exporter.get_exports()) >= 1
    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.name == "test_counter"
    assert metric.data.data_points[0].value == 100


def test_periodic_reader_force_flush():
    exporter = FakeExporter()
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60_000)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_counter(name="flush_counter")
    counter.add(50)

    # Force flush should export immediately
    reader.force_flush()

    assert len(exporter.get_exports()) >= 1
    metrics_data = exporter.get_exports()[0]
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.name == "flush_counter"
    assert metric.data.data_points[0].value == 50

    # Clean up
    reader.shutdown()
