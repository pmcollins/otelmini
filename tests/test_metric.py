from typing import Sequence

from otelmini._lib import Exporter, T, ExportResult
from otelmini.metric import ManualExportingMetricReader, MeterProvider, mk_metric_request
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


def test_mk_metric_request():
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

    request = mk_metric_request(metrics_data)

    assert len(request.resource_metrics) == 1
    proto_resource_metrics = request.resource_metrics[0]
    assert proto_resource_metrics.schema_url == "http://example.com/resource_schema"
    assert len(proto_resource_metrics.resource.attributes) == 1
    assert proto_resource_metrics.resource.attributes[0].key == "service.name"
    assert (
        proto_resource_metrics.resource.attributes[0].value.string_value
        == "test_service"
    )

    assert len(proto_resource_metrics.scope_metrics) == 1
    proto_scope_metrics = proto_resource_metrics.scope_metrics[0]
    assert proto_scope_metrics.schema_url == "http://example.com/schema"
    assert proto_scope_metrics.scope.name == "test.scope"
    assert proto_scope_metrics.scope.version == "0.1.0"

    assert len(proto_scope_metrics.metrics) == 1
    proto_metric = proto_scope_metrics.metrics[0]
    assert proto_metric.name == "test.metric"
    assert proto_metric.description == "A test metric"
    assert proto_metric.unit == "ms"

    proto_sum = proto_metric.sum
    assert proto_sum.is_monotonic is True
    assert (
        proto_sum.aggregation_temporality
        == AggregationTemporality.CUMULATIVE.value
    )

    assert len(proto_sum.data_points) == 1
    proto_data_point = proto_sum.data_points[0]
    assert proto_data_point.start_time_unix_nano == 1678886400000000000
    assert proto_data_point.time_unix_nano == 1678886401000000000
    assert proto_data_point.as_double == 123.45
    assert len(proto_data_point.attributes) == 1
    assert proto_data_point.attributes[0].key == "label"
    assert proto_data_point.attributes[0].value.string_value == "value"


def test_metric():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_counter(name="x")
    counter.add(42)
    reader.force_flush()
    assert len(exporter.get_exports())


class FakeExporter(Exporter):
    def __init__(self):
        self.exports = []

    def export(self, items: Sequence[T]) -> ExportResult:
        self.exports.append(items)
        return ExportResult.SUCCESS

    def get_exports(self):
        return self.exports
