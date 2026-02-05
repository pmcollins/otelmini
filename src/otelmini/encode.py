"""OTLP JSON encoding for traces, logs, and metrics."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Mapping, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from otelmini.log import MiniLogRecord
    from otelmini.point import MetricsData, Sum
    from otelmini.types import MiniSpan, Resource, InstrumentationScope


def encode_trace_request(spans: Sequence[MiniSpan]) -> str:
    """Encode spans to OTLP JSON format."""
    return json.dumps({"resourceSpans": _encode_resource_spans(spans)})


def encode_logs_request(logs: Sequence[MiniLogRecord]) -> str:
    """Encode logs to OTLP JSON format."""
    return json.dumps({"resourceLogs": _encode_resource_logs(logs)})


def encode_metrics_request(metrics_data: MetricsData) -> str:
    """Encode metrics to OTLP JSON format."""
    return json.dumps({"resourceMetrics": _encode_resource_metrics(metrics_data)})


def _encode_resource_spans(spans: Sequence[MiniSpan]) -> list[dict]:
    """Group spans by resource and scope, encode to OTLP structure."""
    grouped = defaultdict(lambda: defaultdict(list))
    for span in spans:
        resource = span.get_resource()
        scope = span.get_instrumentation_scope()
        grouped[id(resource), resource][id(scope), scope].append(span)

    resource_spans = []
    for (_, resource), scopes in grouped.items():
        scope_spans = []
        for (_, scope), scope_span_list in scopes.items():
            scope_spans.append({
                "scope": _encode_scope(scope),
                "spans": [_encode_span(s) for s in scope_span_list],
            })
        resource_spans.append({
            "resource": _encode_resource(resource),
            "scopeSpans": scope_spans,
            "schemaUrl": resource.get_schema_url() or "",
        })
    return resource_spans


def _encode_resource_logs(logs: Sequence[MiniLogRecord]) -> list[dict]:
    """Encode logs to OTLP structure (simplified: one resource per log)."""
    resource_logs = []
    for log in logs:
        resource_logs.append({
            "resource": {"attributes": []},
            "scopeLogs": [{
                "scope": {},
                "logRecords": [_encode_log_record(log)],
            }],
        })
    return resource_logs


def _encode_resource_metrics(metrics_data: MetricsData) -> list[dict]:
    """Encode metrics data to OTLP structure."""
    resource_metrics = []
    for rm in metrics_data.resource_metrics:
        scope_metrics = []
        for sm in rm.scope_metrics:
            metrics = []
            for metric in sm.metrics:
                encoded_metric = _encode_metric(metric)
                if encoded_metric:
                    metrics.append(encoded_metric)
            scope_metrics.append({
                "scope": _encode_scope(sm.scope),
                "metrics": metrics,
                "schemaUrl": sm.schema_url or "",
            })
        resource_metrics.append({
            "resource": _encode_resource(rm.resource),
            "scopeMetrics": scope_metrics,
            "schemaUrl": rm.schema_url or "",
        })
    return resource_metrics


def _encode_resource(resource: Resource) -> dict:
    """Encode resource to OTLP format."""
    return {"attributes": _encode_attributes(resource.get_attributes())}


def _encode_scope(scope: InstrumentationScope) -> dict:
    """Encode instrumentation scope to OTLP format."""
    result = {"name": scope.name or ""}
    if scope.version:
        result["version"] = scope.version
    return result


def _encode_event(event: tuple) -> dict:
    """Encode a span event to OTLP format."""
    name, attributes, timestamp = event
    result = {"name": name}
    if timestamp is not None:
        result["timeUnixNano"] = str(timestamp)
    if attributes:
        result["attributes"] = _encode_attributes(attributes)
    return result


def _encode_span(span: MiniSpan) -> dict:
    """Encode a single span to OTLP format."""
    ctx = span.get_span_context()
    result = {
        "traceId": _encode_trace_id(ctx.trace_id),
        "spanId": _encode_span_id(ctx.span_id),
        "name": span.get_name(),
        "kind": 1,  # SPAN_KIND_INTERNAL
        "startTimeUnixNano": str(span.get_start_time()),
        "endTimeUnixNano": str(span.get_end_time() or 0),
        "attributes": _encode_attributes(span.get_attributes()),
        "status": {},
    }
    parent_span_id = span.get_parent_span_id()
    if parent_span_id:
        result["parentSpanId"] = _encode_span_id(parent_span_id)
    events = span.get_events()
    if events:
        result["events"] = [_encode_event(e) for e in events]
    return result


def _encode_log_record(log: MiniLogRecord) -> dict:
    """Encode a single log record to OTLP format."""
    return {
        "timeUnixNano": str(log.timestamp or 0),
        "severityNumber": log.severity_number.value if log.severity_number else 0,
        "severityText": log.severity_text or "",
        "body": {"stringValue": str(log.body) if log.body else ""},
        "attributes": _encode_attributes(log.attributes or {}),
    }


def _encode_metric(metric) -> Optional[dict]:
    """Encode a single metric to OTLP format."""
    from otelmini.point import Sum, Gauge, Histogram

    base = {
        "name": metric.name,
        "description": metric.description or "",
        "unit": metric.unit or "",
    }

    if isinstance(metric.data, Sum):
        data_points = []
        for point in metric.data.data_points:
            data_points.append({
                "attributes": _encode_attributes(point.attributes),
                "startTimeUnixNano": str(point.start_time_unix_nano),
                "timeUnixNano": str(point.time_unix_nano),
                "asDouble": point.value,
            })
        base["sum"] = {
            "dataPoints": data_points,
            "aggregationTemporality": metric.data.aggregation_temporality.value,
            "isMonotonic": metric.data.is_monotonic,
        }
        return base

    if isinstance(metric.data, Gauge):
        data_points = []
        for point in metric.data.data_points:
            data_points.append({
                "attributes": _encode_attributes(point.attributes),
                "startTimeUnixNano": str(point.start_time_unix_nano),
                "timeUnixNano": str(point.time_unix_nano),
                "asDouble": point.value,
            })
        base["gauge"] = {
            "dataPoints": data_points,
        }
        return base

    if isinstance(metric.data, Histogram):
        data_points = []
        for point in metric.data.data_points:
            data_points.append({
                "attributes": _encode_attributes(point.attributes),
                "startTimeUnixNano": str(point.start_time_unix_nano),
                "timeUnixNano": str(point.time_unix_nano),
                "count": str(point.count),
                "sum": point.sum,
                "bucketCounts": [str(c) for c in point.bucket_counts],
                "explicitBounds": list(point.explicit_bounds),
                "min": point.min,
                "max": point.max,
            })
        base["histogram"] = {
            "dataPoints": data_points,
            "aggregationTemporality": metric.data.aggregation_temporality.value,
        }
        return base

    return None


def _encode_attributes(attributes: Optional[Mapping[str, Any]]) -> list[dict]:
    """Encode attributes to OTLP format."""
    if not attributes:
        return []
    return [{"key": k, "value": _encode_value(v)} for k, v in attributes.items()]


def _encode_value(value: Any) -> dict:
    """Encode a single attribute value to OTLP AnyValue format."""
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, bytes):
        return {"bytesValue": value.decode("utf-8", errors="replace")}
    if isinstance(value, (list, tuple)):
        return {"arrayValue": {"values": [_encode_value(v) for v in value]}}
    if isinstance(value, Mapping):
        return {"kvlistValue": {"values": [{"key": str(k), "value": _encode_value(v)} for k, v in value.items()]}}
    # Fallback to string
    return {"stringValue": str(value)}


def _encode_trace_id(trace_id: int) -> str:
    """Encode trace ID as lowercase hex string."""
    return format(trace_id, "032x")


def _encode_span_id(span_id: int) -> str:
    """Encode span ID as lowercase hex string."""
    return format(span_id, "016x")
