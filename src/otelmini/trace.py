from __future__ import annotations

import logging
import time
import typing
from collections import defaultdict
from http.client import BAD_GATEWAY, GATEWAY_TIMEOUT, OK, SERVICE_UNAVAILABLE, TOO_MANY_REQUESTS, HTTPConnection
from typing import TYPE_CHECKING, Any, Iterator, Mapping, Optional, Sequence
from urllib.parse import urlparse

from opentelemetry import trace
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
from opentelemetry.trace import Link, SpanKind, StatusCode, Tracer, TracerProvider, _Links
from opentelemetry.trace import Span as ApiSpan
from opentelemetry.trace.span import SpanContext, Status, TraceState
from opentelemetry.util._decorator import _agnosticcontextmanager

from otelmini._lib import Exporter, ExportResult, Retrier, RetrierResult, SingleAttemptResult, _HttpExporter
from otelmini.pb import mk_trace_request, encode_attributes, encode_key_value, encode_value, EncodingError
from otelmini.types import MiniSpan, InstrumentationScope, Resource

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.util import types
    from opentelemetry.util.types import Attributes

    from otelmini.processor import Processor

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


class HttpSpanExporter(Exporter[MiniSpan]):
    def __init__(self, endpoint="http://localhost:4318/v1/traces", timeout=30):
        self._exporter = _HttpExporter(endpoint, timeout)

    def export(self, items: Sequence[MiniSpan]) -> ExportResult:
        request = mk_trace_request(items)
        return self._exporter.export(request)


class GrpcSpanExporter(Exporter[MiniSpan]):
    def __init__(self, addr="127.0.0.1:4317", max_retries=3, channel_provider=None, sleep=time.sleep):
        self.addr = addr
        self.max_retries = max_retries
        self.channel_provider = channel_provider
        self.sleep = sleep
        self.exporter = None
        self.init_grpc()  # this would need to be called lazily for this class to be serializable for multiprocessing

    def init_grpc(self):
        if self.exporter:
            return

        from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub

        from otelmini._grpclib import GrpcExporter

        self.exporter = GrpcExporter(
            addr=self.addr,
            max_retries=self.max_retries,
            channel_provider=self.channel_provider,
            sleep=self.sleep,
            stub_class=TraceServiceStub,
        )

    def export(self, spans: Sequence[MiniSpan]) -> ExportResult:
        self.init_grpc()
        req = mk_trace_request(spans)
        return self.exporter.export(req)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.exporter.force_flush(timeout_millis)

    def shutdown(self) -> None:
        if self.exporter is not None:
            self.exporter.shutdown()
            self.exporter = None

    def __setstate__(self, state):
        self.__dict__.update(state)
        # self.init_grpc()  # this would have to be called for this class to wake up after being deserialized


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


def encode_trace_id(trace_id: int) -> bytes:
    return trace_id.to_bytes(length=16, byteorder="big", signed=False)
