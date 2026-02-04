import json
from typing import Sequence

from otelmini._lib import Exporter, T, ExportResult
from otelmini.metric import ManualExportingMetricReader, MeterProvider
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


class FakeExporter(Exporter):
    def __init__(self):
        self.exports = []

    def export(self, items: Sequence[T]) -> ExportResult:
        self.exports.append(items)
        return ExportResult.SUCCESS

    def get_exports(self):
        return self.exports
