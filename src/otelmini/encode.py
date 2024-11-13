import logging
from collections import defaultdict
from typing import (
    Any,
    List,
    Mapping,
    Optional,
    Sequence,
)

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
from opentelemetry.sdk.trace import Event, ReadableSpan, Resource
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import SpanContext, Status, TraceState
from opentelemetry.util.types import Attributes

_logger = logging.getLogger(__name__)


def mk_trace_request(spans: Sequence[ReadableSpan]) -> PB2ExportTraceServiceRequest:
    return PB2ExportTraceServiceRequest(
        resource_spans=_encode_resource_spans(spans)
    )


def _encode_resource_spans(
    sdk_spans: Sequence[ReadableSpan],
) -> List[PB2ResourceSpans]:
    sdk_resource_spans = defaultdict(lambda: defaultdict(list))

    for sdk_span in sdk_spans:
        sdk_resource = sdk_span.resource
        sdk_instrumentation = sdk_span.instrumentation_scope or None
        pb2_span = _encode_span(sdk_span)

        sdk_resource_spans[sdk_resource][sdk_instrumentation].append(pb2_span)

    pb2_resource_spans = []

    for sdk_resource, sdk_instrumentations in sdk_resource_spans.items():
        scope_spans = []
        for sdk_instrumentation, pb2_spans in sdk_instrumentations.items():
            scope_spans.append(
                PB2ScopeSpans(
                    scope=(_encode_instrumentation_scope(sdk_instrumentation)),
                    spans=pb2_spans,
                )
            )
        pb2_resource_spans.append(
            PB2ResourceSpans(
                resource=_encode_resource(sdk_resource),
                scope_spans=scope_spans,
                schema_url=sdk_resource.schema_url,
            )
        )

    return pb2_resource_spans


def _encode_resource(resource: Resource) -> PB2Resource:
    return PB2Resource(attributes=_encode_attributes(resource.attributes))


def _encode_instrumentation_scope(
    instrumentation_scope: InstrumentationScope,
) -> PB2InstrumentationScope:
    if instrumentation_scope is None:
        return PB2InstrumentationScope()
    return PB2InstrumentationScope(
        name=instrumentation_scope.name,
        version=instrumentation_scope.version,
    )


def _span_flags(parent_span_context: Optional[SpanContext]) -> int:
    flags = PB2SpanFlags.SPAN_FLAGS_CONTEXT_HAS_IS_REMOTE_MASK
    if parent_span_context and parent_span_context.is_remote:
        flags |= PB2SpanFlags.SPAN_FLAGS_CONTEXT_IS_REMOTE_MASK
    return flags


_SPAN_KIND_MAP = {
    SpanKind.INTERNAL: PB2SPan.SpanKind.SPAN_KIND_INTERNAL,
    SpanKind.SERVER: PB2SPan.SpanKind.SPAN_KIND_SERVER,
    SpanKind.CLIENT: PB2SPan.SpanKind.SPAN_KIND_CLIENT,
    SpanKind.PRODUCER: PB2SPan.SpanKind.SPAN_KIND_PRODUCER,
    SpanKind.CONSUMER: PB2SPan.SpanKind.SPAN_KIND_CONSUMER,
}


def _encode_span(sdk_span: ReadableSpan) -> PB2SPan:
    print(f"span name {sdk_span.name}")
    span_context = sdk_span.get_span_context()
    return PB2SPan(
        trace_id=_encode_trace_id(span_context.trace_id),
        span_id=_encode_span_id(span_context.span_id),
        trace_state=_encode_trace_state(span_context.trace_state),
        parent_span_id=_encode_parent_id(sdk_span.parent),
        name=sdk_span.name,
        kind=_SPAN_KIND_MAP[sdk_span.kind],
        start_time_unix_nano=sdk_span.start_time,
        end_time_unix_nano=sdk_span.end_time,
        attributes=_encode_attributes(sdk_span.attributes),
        events=_encode_events(sdk_span.events),
        links=_encode_links(sdk_span.links),
        status=_encode_status(sdk_span.status),
        dropped_attributes_count=sdk_span.dropped_attributes,
        dropped_events_count=sdk_span.dropped_events,
        dropped_links_count=sdk_span.dropped_links,
        flags=_span_flags(sdk_span.parent),
    )


def _encode_attributes(
    attributes: Attributes,
) -> Optional[List[PB2KeyValue]]:
    if attributes:
        pb2_attributes = []
        for key, value in attributes.items():
            # pylint: disable=broad-exception-caught
            try:
                pb2_attributes.append(_encode_key_value(key, value))
            except Exception as error:
                _logger.exception("Failed to encode key %s: %s", key, error)
    else:
        pb2_attributes = None
    return pb2_attributes


def _encode_events(
    events: Sequence[Event],
) -> Optional[List[PB2SPan.Event]]:
    pb2_events = None
    if events:
        pb2_events = []
        for event in events:
            encoded_event = PB2SPan.Event(
                name=event.name,
                time_unix_nano=event.timestamp,
                attributes=_encode_attributes(event.attributes),
                dropped_attributes_count=event.dropped_attributes,
            )
            pb2_events.append(encoded_event)
    return pb2_events


def _encode_links(links: Sequence[Link]) -> Sequence[PB2SPan.Link]:
    pb2_links = None
    if links:
        pb2_links = []
        for link in links:
            encoded_link = PB2SPan.Link(
                trace_id=_encode_trace_id(link.context.trace_id),
                span_id=_encode_span_id(link.context.span_id),
                attributes=_encode_attributes(link.attributes),
                dropped_attributes_count=link.dropped_attributes,
                flags=_span_flags(link.context),
            )
            pb2_links.append(encoded_link)
    return pb2_links


def _encode_status(status: Status) -> Optional[PB2Status]:
    pb2_status = None
    if status is not None:
        pb2_status = PB2Status(
            code=status.status_code.value,
            message=status.description,
        )
    return pb2_status


def _encode_trace_state(trace_state: TraceState) -> Optional[str]:
    pb2_trace_state = None
    if trace_state is not None:
        pb2_trace_state = ",".join(
            [f"{key}={value}" for key, value in (trace_state.items())]
        )
    return pb2_trace_state


def _encode_parent_id(context: Optional[SpanContext]) -> Optional[bytes]:
    if context:
        return _encode_span_id(context.span_id)
    return None


def _encode_span_id(span_id: int) -> bytes:
    return span_id.to_bytes(length=8, byteorder="big", signed=False)


def _encode_key_value(key: str, value: Any) -> PB2KeyValue:
    return PB2KeyValue(key=key, value=_encode_value(value))


def _encode_trace_id(trace_id: int) -> bytes:
    return trace_id.to_bytes(length=16, byteorder="big", signed=False)


def _encode_value(value: Any) -> PB2AnyValue:
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
        return PB2AnyValue(
            array_value=PB2ArrayValue(values=[_encode_value(v) for v in value])
        )
    elif isinstance(value, Mapping):
        return PB2AnyValue(
            kvlist_value=PB2KeyValueList(
                values=[_encode_key_value(str(k), v) for k, v in value.items()]
            )
        )
    raise Exception(f"Invalid type {type(value)} of value {value}")
