from __future__ import annotations

import logging
import time
import typing
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Optional, Sequence, Dict

from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest as PB2ExportTraceServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
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
from opentelemetry.trace import Link, SpanKind, StatusCode, _Links
from opentelemetry.trace import Span as ApiSpan
from opentelemetry.trace import SpanContext as ApiSpanContext
from opentelemetry.trace import Tracer
from opentelemetry.trace import TracerProvider
from opentelemetry.trace.span import SpanContext, Status, TraceState
from opentelemetry.util._decorator import _agnosticcontextmanager

from otelmini._lib import Exporter, ExportResult
from otelmini._grpclib import GrpcExporter

if TYPE_CHECKING:
    from otelmini.processor import Processor
    from opentelemetry.context import Context
    from opentelemetry.util import types
    from opentelemetry.util.types import Attributes

_pylogger = logging.getLogger(__package__)
_tracer = trace.get_tracer(__package__)


class MiniTracerProvider(TracerProvider):
    def __init__(self, span_processor=None):
        self.span_processor = span_processor

    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: typing.Optional[str] = None,
        schema_url: typing.Optional[str] = None,
        attributes: typing.Optional[types.Attributes] = None,
    ) -> MiniTracer:
        return MiniTracer(self.span_processor)

    def shutdown(self):
        pass


class MiniTracer(Tracer):
    def __init__(self, span_processor: Processor[MiniSpan]):
        self.span_processor = span_processor

    def start_span(
        self,
        name: str,
        context: Optional[Context] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: types.Attributes = None,
        links: _Links = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,  # noqa: FBT001, FBT002
        set_status_on_exception: bool = True,  # noqa: FBT001, FBT002
    ) -> ApiSpan:
        span = MiniSpan(
            name, SpanContext(0, 0, False), Resource(""), InstrumentationScope("", ""), self.span_processor.on_end
        )
        self.span_processor.on_start(span)
        return span

    @_agnosticcontextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Optional[Context] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: types.Attributes = None,
        links: _Links = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,  # noqa: FBT001, FBT002
        set_status_on_exception: bool = True,  # noqa: FBT001, FBT002
        end_on_exit: bool = True,  # noqa: FBT001, FBT002
    ) -> Iterator[ApiSpan]:
        span = self.start_span(name, context, kind, attributes, links, start_time, end_on_exit)
        with trace.use_span(span, end_on_exit=True) as active_span:
            yield active_span


class InstrumentationScope:
    def __init__(self, name, version):
        self.name = name
        self.version = version

    def get_name(self):
        return self.name

    def get_version(self):
        return self.version


class MiniSpan(ApiSpan):
    def __init__(
        self,
        name,
        span_context: SpanContext,
        resource: Resource,
        instrumentation_scope: InstrumentationScope,
        on_end_callback: typing.Callable[[MiniSpan], None],
    ):
        self._name = name
        self._span_context = span_context
        self._resource = resource
        self._instrumentation_scope = instrumentation_scope
        self._on_end_callback = on_end_callback
        self._attributes = {}
        self._events = []
        self._status = None
        self._status_description = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end()

    def get_name(self):
        return self._name

    def get_resource(self):
        return self._resource

    def get_instrumentation_scope(self):
        return self._instrumentation_scope

    def get_span_context(self) -> ApiSpanContext:
        return self._span_context

    def set_attributes(self, attributes: typing.Mapping[str, types.AttributeValue]) -> None:
        self._attributes.update(attributes)

    def set_attribute(self, key: str, value: types.AttributeValue) -> None:
        self._attributes[key] = value

    def add_event(self, name: str, attributes: types.Attributes = None, timestamp: typing.Optional[int] = None) -> None:
        self._events.append((name, attributes, timestamp))

    def update_name(self, name: str) -> None:
        self._name = name

    def is_recording(self) -> bool:
        return self._status is None

    def set_status(self, status: typing.Union[Status, StatusCode], description: typing.Optional[str] = None) -> None:
        self._status = status
        self._status_description = description

    def record_exception(
        self,
        exception: BaseException,
        attributes: types.Attributes = None,
        timestamp: typing.Optional[int] = None,
        escaped: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        self._events.append((exception.__class__.__name__, attributes, timestamp))

    def end(self, end_time: typing.Optional[int] = None) -> None:
        self._on_end_callback(self)

    def to_dict(self) -> Dict[str, Any]:
        """Convert a MiniSpan to a serializable dictionary."""
        return {
            "name": self.get_name(),
            "trace_id": self.get_span_context().trace_id,
            "span_id": self.get_span_context().span_id,
            "attributes": self._attributes,
            "events": self._events,
            "status": self._status,
            "status_description": self._status_description
        }


class GrpcSpanExporter(Exporter[MiniSpan]):
    def __init__(self, addr="127.0.0.1:4317", max_retries=3, channel_provider=None, sleep=time.sleep):
        self.addr = addr
        self.max_retries = max_retries
        self.channel_provider = channel_provider
        self.sleep = sleep
        self.exporter = None

    def __setstate__(self, state):
        print("__setstate__")
        self.__dict__.update(state)
        # self.init_grpc()

    def init_grpc(self):
        if self.exporter:
            return
        self.exporter = GrpcExporter(
            addr=self.addr,
            max_retries=self.max_retries,
            channel_provider=self.channel_provider,
            sleep=self.sleep,
            stub_class=TraceServiceStub,
            response_handler=handle_trace_response,
        )
        self.exporter.connect()

    def export(self, spans: Sequence[MiniSpan]) -> ExportResult:
        self.init_grpc()
        req = mk_trace_request(spans)
        return self.exporter.export_request(req)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.exporter.force_flush(timeout_millis)

    def shutdown(self) -> None:
        if self.exporter is not None:
            self.exporter.shutdown()
            self.exporter = None


class Resource:
    def __init__(self, schema_url: str = ""):
        self._schema_url = schema_url
        self._attributes = {}

    def get_attributes(self):
        return self._attributes

    def get_schema_url(self):
        return self._schema_url

    def __getstate__(self):
        return {
            "schema_url": self._schema_url,
            "attributes": self._attributes
        }

    def __setstate__(self, state):
        self._schema_url = state["schema_url"]
        self._attributes = state["attributes"]


def handle_trace_response(resp):
    if resp.HasField("partial_success") and resp.partial_success:
        ps = resp.partial_success
        msg = f"partial success: rejected_spans: [{ps.rejected_spans}], error_message: [{ps.error_message}]"
        _pylogger.warning(msg)


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
        name=instrumentation_scope.get_name(),
        version=instrumentation_scope.get_version(),
    )


def span_flags(parent_span_context: Optional[SpanContext]) -> int:
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


def encode_span(span: MiniSpan) -> PB2SPan:
    span_context = span.get_span_context()
    return PB2SPan(
        trace_id=encode_trace_id(span_context.trace_id),
        span_id=encode_span_id(span_context.span_id),
        trace_state=encode_trace_state(span_context.trace_state),
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
    attributes: Attributes,
) -> Optional[list[PB2KeyValue]]:
    if attributes:
        pb2_attributes = []
        for key, value in attributes.items():
            try:
                pb2_attributes.append(encode_key_value(key, value))
            except Exception:
                _pylogger.exception("Failed to encode key %s", key)
    else:
        pb2_attributes = None
    return pb2_attributes


# def encode_events(events: Sequence[Event],) -> Optional[list[PB2SPan.Event]]:
#     pb2_events = None
#     if events:
#         pb2_events = []
#         for event in events:
#             encoded_event = PB2SPan.Event(
#                 name=event.name,
#                 time_unix_nano=event.timestamp,
#                 attributes=encode_attributes(event.attributes),
#                 dropped_attributes_count=event.dropped_attributes,
#             )
#             pb2_events.append(encoded_event)
#     return pb2_events


def encode_links(links: Sequence[Link]) -> Sequence[PB2SPan.Link]:
    pb2_links = None
    if links:
        pb2_links = []
        for link in links:
            encoded_link = PB2SPan.Link(
                trace_id=encode_trace_id(link.context.trace_id),
                span_id=encode_span_id(link.context.span_id),
                attributes=encode_attributes(link.attributes),
                dropped_attributes_count=link.dropped_attributes,
                flags=span_flags(link.context),
            )
            pb2_links.append(encoded_link)
    return pb2_links


def encode_status(status: Status) -> Optional[PB2Status]:
    pb2_status = None
    if status is not None:
        pb2_status = PB2Status(
            code=status.status_code.value,
            message=status.description,
        )
    return pb2_status


def encode_trace_state(trace_state: TraceState) -> Optional[str]:
    pb2_trace_state = None
    if trace_state is not None:
        pb2_trace_state = ",".join([f"{key}={value}" for key, value in (trace_state.items())])
    return pb2_trace_state


def encode_parent_id(context: Optional[SpanContext]) -> Optional[bytes]:
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
