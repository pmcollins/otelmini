from collections import defaultdict
from typing import Any, Mapping, Optional, Sequence

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest as PB2ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue as PB2AnyValue
from opentelemetry.proto.common.v1.common_pb2 import ArrayValue as PB2ArrayValue
from opentelemetry.proto.common.v1.common_pb2 import InstrumentationScope as PB2InstrumentationScope
from opentelemetry.proto.common.v1.common_pb2 import KeyValue as PB2KeyValue
from opentelemetry.proto.common.v1.common_pb2 import KeyValueList as PB2KeyValueList
from opentelemetry.proto.resource.v1.resource_pb2 import (
    Resource as PB2Resource,
)
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans as PB2ResourceSpans
from opentelemetry.proto.trace.v1.trace_pb2 import ScopeSpans as PB2ScopeSpans
from opentelemetry.proto.trace.v1.trace_pb2 import Span as PB2SPan
from opentelemetry.proto.trace.v1.trace_pb2 import SpanFlags as PB2SpanFlags
from opentelemetry.proto.trace.v1.trace_pb2 import Status as PB2Status
from opentelemetry.trace import Link, SpanKind

from otelmini.types import InstrumentationScope, MiniSpan, Resource


def mk_trace_request(spans: Sequence[MiniSpan]) -> PB2ExportTraceServiceRequest:
    return PB2ExportTraceServiceRequest(resource_spans=encode_resource_spans(spans))

def encode_resource_spans(spans: Sequence[MiniSpan]) -> list[PB2ResourceSpans]:
    sdk_resource_spans = defaultdict(lambda: defaultdict(list))
    for span in spans:
        resource = span.get_resource()
        instrumentation_scope = span.get_instrumentation_scope()
        pb2_span = encode_span(span)
        sdk_resource_spans[resource][instrumentation_scope].append(pb2_span)
    pb2_resource_spans = []
    for resource, sdk_instrumentations in sdk_resource_spans.items():
        scope_spans = []
        for instrumentation_scope, pb2_spans in sdk_instrumentations.items():
            scope_spans.append(
                PB2ScopeSpans(
                    scope=(encode_instrumentation_scope(instrumentation_scope)),
                    spans=pb2_spans,
                )
            )
        pb2_resource_spans.append(
            PB2ResourceSpans(
                resource=encode_resource(resource),
                scope_spans=scope_spans,
                schema_url=resource.get_schema_url(),
            )
        )
    return pb2_resource_spans

def encode_resource(resource: Resource) -> PB2Resource:
    return PB2Resource(attributes=encode_attributes(resource.get_attributes()))

def encode_instrumentation_scope(instrumentation_scope: InstrumentationScope) -> PB2InstrumentationScope:
    return PB2InstrumentationScope(
        name=instrumentation_scope.name,
        version=instrumentation_scope.version,
    )

def span_flags(parent_span_context: Optional[Any]) -> int:
    flags = PB2SpanFlags.SPAN_FLAGS_CONTEXT_HAS_IS_REMOTE_MASK
    if parent_span_context and getattr(parent_span_context, 'is_remote', False):
        flags |= PB2SpanFlags.SPAN_FLAGS_CONTEXT_IS_REMOTE_MASK
    return flags

_SPAN_KIND_MAP = {
    SpanKind.INTERNAL: PB2SPan.SpanKind.SPAN_KIND_INTERNAL,
    SpanKind.SERVER: PB2SPan.SpanKind.SPAN_KIND_SERVER,
    SpanKind.CLIENT: PB2SPan.SpanKind.SPAN_KIND_CLIENT,
    SpanKind.PRODUCER: PB2SPan.SpanKind.SPAN_KIND_PRODUCER,
    SpanKind.CONSUMER: PB2SPan.SpanKind.SPAN_KIND_CONSUMER,
}

def encode_span(span: MiniSpan) -> PB2SPan:
    span_context = span.get_span_context()
    return PB2SPan(
        trace_id=encode_trace_id(span_context.trace_id),
        span_id=encode_span_id(span_context.span_id),
        trace_state=encode_trace_state(getattr(span_context, 'trace_state', None)),
        name=span.get_name(),
        # parent_span_id=encode_parent_id(span.parent),
        # kind=_SPAN_KIND_MAP[span.kind],
        # start_time_unix_nano=span.start_time,
        # end_time_unix_nano=span.end_time,
        # attributes=encode_attributes(span.attributes),
        # events=encode_events(span.events),
        # links=encode_links(span.links),
        # status=encode_status(span.status),
        # dropped_attributes_count=span.dropped_attributes,
        # dropped_events_count=span.dropped_events,
        # dropped_links_count=span.dropped_links,
        # flags=_span_flags(span.parent),
    )

def encode_attributes(
    attributes: dict,
) -> Optional[list[PB2KeyValue]]:
    if attributes:
        pb2_attributes = []
        for key, value in attributes.items():
            try:
                pb2_attributes.append(encode_key_value(key, value))
            except Exception:
                pass  # Logging is handled in the caller
    else:
        pb2_attributes = None
    return pb2_attributes

def encode_links(links: Sequence[Link]) -> Sequence[PB2SPan.Link]:
    pb2_links = None
    if links:
        pb2_links = []
        for link in links:
            encoded_link = PB2SPan.Link(
                trace_id=encode_trace_id(link.context.trace_id),
                span_id=encode_span_id(link.context.span_id),
                attributes=encode_attributes(link.attributes),
                dropped_attributes_count=getattr(link, 'dropped_attributes', 0),
                flags=span_flags(getattr(link, 'context', None)),
            )
            pb2_links.append(encoded_link)
    return pb2_links

def encode_status(status: Any) -> Optional[PB2Status]:
    pb2_status = None
    if status is not None:
        pb2_status = PB2Status(
            code=getattr(status, 'status_code', None).value if hasattr(status, 'status_code') else None,
            message=getattr(status, 'description', None),
        )
    return pb2_status

def encode_trace_state(trace_state: Any) -> Optional[str]:
    pb2_trace_state = None
    if trace_state is not None:
        pb2_trace_state = ",".join([f"{key}={value}" for key, value in (trace_state.items())])
    return pb2_trace_state

def encode_parent_id(context: Optional[Any]) -> Optional[bytes]:
    if context:
        return encode_span_id(context.span_id)
    return None

def encode_span_id(span_id: int) -> bytes:
    return span_id.to_bytes(length=8, byteorder="big", signed=False)

def encode_key_value(key: str, value: Any) -> PB2KeyValue:
    return PB2KeyValue(key=key, value=encode_value(value))

def encode_trace_id(trace_id: int) -> bytes:
    return trace_id.to_bytes(length=16, byteorder="big", signed=False)

def encode_value(value: Any) -> PB2AnyValue:
    if isinstance(value, bool):
        return PB2AnyValue(bool_value=value)
    if isinstance(value, str):
        return PB2AnyValue(string_value=value)
    if isinstance(value, int):
        return PB2AnyValue(int_value=value)
    if isinstance(value, float):
        return PB2AnyValue(double_value=value)
    if isinstance(value, bytes):
        return PB2AnyValue(bytes_value=value)
    if isinstance(value, Sequence):
        return PB2AnyValue(array_value=PB2ArrayValue(values=[encode_value(v) for v in value]))
    if isinstance(value, Mapping):
        return PB2AnyValue(kvlist_value=PB2KeyValueList(values=[encode_key_value(str(k), v) for k, v in value.items()]))
    raise EncodingError(value)

class EncodingError(Exception):
    def __init__(self, value):
        super().__init__(f"Invalid type {type(value)} of value {value}")
