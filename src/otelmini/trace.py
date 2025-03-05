from __future__ import annotations

import atexit
import logging
import threading
import time
import typing
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Iterator, Mapping, Optional, Sequence, TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest as PB2ExportTraceServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
from opentelemetry.proto.common.v1.common_pb2 import AnyValue as PB2AnyValue, ArrayValue as PB2ArrayValue, \
    InstrumentationScope as PB2InstrumentationScope, KeyValue as PB2KeyValue, KeyValueList as PB2KeyValueList
from opentelemetry.proto.resource.v1.resource_pb2 import (
    Resource as PB2Resource,
)
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans as PB2ResourceSpans, ScopeSpans as PB2ScopeSpans, \
    Span as PB2SPan, SpanFlags as PB2SpanFlags, Status as PB2Status
from opentelemetry.trace import _Links, Link, Span as ApiSpan, SpanContext, SpanContext as ApiSpanContext, SpanKind, \
    Status, StatusCode, Tracer as ApiTracer, TracerProvider as ApiTracerProvider
from opentelemetry.util import types
from opentelemetry.util._decorator import _agnosticcontextmanager

from otelmini.grpc import GrpcExporter, GrpcExportResult

if TYPE_CHECKING:
    from opentelemetry.trace.span import SpanContext, Status, TraceState
    from opentelemetry.util.types import Attributes

_pylogger = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)


class SpanProcessor(ABC):

    @abstractmethod
    def on_start(self, span: MiniSpan) -> None:
        pass

    @abstractmethod
    def on_end(self, span) -> None:
        pass


class BatchProcessor(SpanProcessor):
    def __init__(self, exporter: SpanExporter, batch_size, interval_seconds):
        self.exporter = exporter
        self.batcher = Batcher(batch_size)
        self.stop = threading.Event()

        self.timer = Timer(self._export, interval_seconds)
        self.timer.start()

    def on_start(self, span: MiniSpan) -> None:
        pass

    def on_end(self, span) -> None:
        if not self.stop.is_set():
            batched = self.batcher.add(span)
            if batched:
                self.timer.notify_sleeper()

    def _export(self):
        batch = self.batcher.pop()
        if batch is not None and len(batch) > 0:
            self.exporter.export(batch)

    def shutdown(self) -> None:
        self.stop.set()
        self.timer.stop()

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        return False


class Batcher:
    def __init__(self, batch_size):
        self.lock = threading.RLock()
        self.batch_size = batch_size
        self.items = []
        self.batches = []

    def add(self, item):
        with self.lock:
            self.items.append(item)
            if len(self.items) == self.batch_size:
                self._batch()
                return True
            return False

    def pop(self):
        with self.lock:
            self._batch()
            return self.batches.pop(0) if len(self.batches) > 0 else None

    def _batch(self):
        self.batches.append(self.items)
        self.items = []


class Timer:
    def __init__(self, target_fcn, interval_seconds):
        self.thread = threading.Thread(target=self._target, daemon=True)
        self.target_fcn = target_fcn
        self.interval_seconds = interval_seconds
        self.sleeper = threading.Condition()
        self.stopper = threading.Event()

        atexit.register(self.stop)

    def start(self):
        self.thread.start()

    def _target(self):
        while not self.stopper.is_set():
            self._sleep()
            if not self.stopper.is_set():
                self.target_fcn()

    def _sleep(self):
        with self.sleeper:
            self.sleeper.wait(self.interval_seconds)

    def notify_sleeper(self):
        with self.sleeper:
            self.sleeper.notify()

    def stop(self):
        self.stopper.set()
        self.notify_sleeper()
        self.target_fcn()

    def join(self):
        self.thread.join()


class TracerProvider(ApiTracerProvider):

    def __init__(self, span_processor=None):
        self.span_processor = span_processor

    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: typing.Optional[str] = None,
        schema_url: typing.Optional[str] = None,
        attributes: typing.Optional[types.Attributes] = None,
    ) -> Tracer:
        return Tracer(self.span_processor)

    def shutdown(self):
        pass


class Tracer(ApiTracer):

    def __init__(self, span_processor: SpanProcessor):
        self.span_processor = span_processor

    def start_span(
        self,
        name: str,
        context: Optional[Context] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: types.Attributes = None,
        links: _Links = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True
    ) -> ApiSpan:
        span = MiniSpan(
            name,
            SpanContext(0, 0, False),
            Resource(""),
            InstrumentationScope("", ""),
            self.span_processor.on_end
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
        record_exception: bool = True,
        set_status_on_exception: bool = True,
        end_on_exit: bool = True
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


class SpanExporter(ABC):
    @abstractmethod
    def export(self, spans: Sequence[MiniSpan]) -> GrpcExportResult:
        pass


class GrpcSpanExporter(SpanExporter):
    def __init__(self, addr="127.0.0.1:4317", max_retries=3, channel_provider=None, sleep=time.sleep):
        self._exporter = GrpcExporter(
            addr=addr,
            max_retries=max_retries,
            channel_provider=channel_provider,
            sleep=sleep,
            stub_class=TraceServiceStub,
            response_handler=handle_trace_response,
        )

    def export(self, spans: Sequence[MiniSpan]) -> GrpcExportResult:
        req = mk_trace_request(spans)
        return self._exporter.export_request(req)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._exporter.force_flush(timeout_millis)

    def shutdown(self) -> None:
        self._exporter.shutdown()


class MiniSpan(ApiSpan):

    def __init__(
        self,
        name,
        span_context: SpanContext,
        resource: Resource,
        instrumentation_scope: InstrumentationScope,
        on_end_callback: typing.Callable[[MiniSpan], None],
    ):
        self.name = name
        self.span_context = span_context
        self.resource = resource
        self.instrumentation_scope = instrumentation_scope
        self.on_end_callback = on_end_callback

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end()

    def get_name(self):
        return self.name

    def get_resource(self):
        return self.resource

    def get_instrumentation_scope(self):
        return self.instrumentation_scope

    def get_span_context(self) -> ApiSpanContext:
        return self.span_context

    def set_attributes(self, attributes: typing.Mapping[str, types.AttributeValue]) -> None:
        pass

    def set_attribute(self, key: str, value: types.AttributeValue) -> None:
        pass

    def add_event(self, name: str, attributes: types.Attributes = None, timestamp: typing.Optional[int] = None) -> None:
        pass

    def update_name(self, name: str) -> None:
        pass

    def is_recording(self) -> bool:
        pass

    def set_status(
        self,
        status: typing.Union[Status, StatusCode],
        description: typing.Optional[str] = None
    ) -> None:
        pass

    def record_exception(
        self, exception: BaseException,
        attributes: types.Attributes = None,
        timestamp: typing.Optional[int] = None,
        escaped: bool = False
    ) -> None:
        pass

    def end(self, end_time: typing.Optional[int] = None) -> None:
        self.on_end_callback(self)


class Resource:

    def __init__(self, schema_url):
        self.schema_url = schema_url

    def get_attributes(self):
        return {}

    def get_schema_url(self):
        return self.schema_url


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
            # pylint: disable=broad-exception-caught
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
        return PB2AnyValue(
            kvlist_value=PB2KeyValueList(values=[encode_key_value(str(k), v) for k, v in value.items()])
        )
    raise EncodingError(value)


class EncodingError(Exception):
    def __init__(self, value):
        super().__init__(f"Invalid type {type(value)} of value {value}")
