from __future__ import annotations

import logging
import random
import time
import typing
from collections import defaultdict
from typing import TYPE_CHECKING, Iterator, Optional, Sequence

from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
from opentelemetry.proto.common.v1.common_pb2 import InstrumentationScope as PB2InstrumentationScope
from opentelemetry.proto.resource.v1.resource_pb2 import (
    Resource as PB2Resource,
)
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans as PB2ResourceSpans
from opentelemetry.proto.trace.v1.trace_pb2 import ScopeSpans as PB2ScopeSpans
from opentelemetry.proto.trace.v1.trace_pb2 import Span as PB2SPan
from opentelemetry.proto.trace.v1.trace_pb2 import SpanFlags as PB2SpanFlags
from opentelemetry.trace import Span as ApiSpan
from opentelemetry.trace import SpanKind, Tracer, TracerProvider, _Links
from opentelemetry.trace.span import SpanContext
from opentelemetry.util._decorator import _agnosticcontextmanager

from otelmini._lib import Exporter, ExportResult, _HttpExporter
from otelmini.pb import encode_attributes, mk_trace_request, pb_encode_span
from otelmini.types import InstrumentationScope, MiniSpan, Resource

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.util import types

    from otelmini.processor import Processor

_pylogger = logging.getLogger(__package__)
_tracer = trace.get_tracer(__package__)


def _generate_trace_id() -> int:
    """Generate a random 128-bit trace ID."""
    return random.getrandbits(128)


def _generate_span_id() -> int:
    """Generate a random 64-bit span ID."""
    return random.getrandbits(64)


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
        if self.span_processor:
            self.span_processor.shutdown()


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
        parent_span_context = trace.get_current_span().get_span_context()
        if parent_span_context.is_valid:
            trace_id = parent_span_context.trace_id
            parent_span_id = parent_span_context.span_id
        else:
            trace_id = _generate_trace_id()
            parent_span_id = None
        span_id = _generate_span_id()
        span_context = SpanContext(trace_id, span_id, is_remote=False)
        span = MiniSpan(
            name, span_context, Resource(""), InstrumentationScope("", ""), self.span_processor.on_end,
            parent_span_id=parent_span_id,
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
            response_class=ExportTraceServiceResponse,
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
        pb2_span = pb_encode_span(span)
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
