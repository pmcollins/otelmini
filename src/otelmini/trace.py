from __future__ import annotations

import logging
import threading
import time
import typing
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Sequence

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
from opentelemetry.trace import _Links, Span as ApiSpan, SpanContext as ApiSpanContext, SpanKind, Status, StatusCode, \
    Tracer as ApiTracer, TracerProvider as ApiTracerProvider
from opentelemetry.util import types

from otelmini._tracelib import Batcher, MiniSpan, mk_trace_request, Timer
from otelmini.grpc import GrpcExporter, GrpcExportResult

_tracer = trace.get_tracer(__name__)
_logger = logging.getLogger(__name__)


class Span(ApiSpan):

    def __init__(self, name):
        self.name = name

    def end(self, end_time: typing.Optional[int] = None) -> None:
        pass

    def get_span_context(self) -> ApiSpanContext:
        pass

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


class SpanProcessor(ABC):

    @abstractmethod
    def on_start(self, span: Span) -> None:
        pass

    @abstractmethod
    def on_end(self, span) -> None:
        pass


class BatchProcessor(SpanProcessor):
    def __init__(self, exporter: SpanExporter, batch_size, interval_seconds):
        self.exporter = exporter
        self.batcher = Batcher(batch_size)
        self.stopper = threading.Event()

        self.timer = Timer(self._export, interval_seconds)
        self.timer.start()

    def on_start(self, span: Span) -> None:
        pass

    def on_end(self, span) -> None:
        if not self.stopper.is_set():
            batched = self.batcher.add(span)
            if batched:
                self.timer.notify_sleeper()

    def _export(self):
        batch = self.batcher.pop()
        if batch is not None and len(batch) > 0:
            self.exporter.export(batch)

    def shutdown(self) -> None:
        self.stopper.set()
        self.timer.stop()

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        return False


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
        span = Span(name)
        self.span_processor.on_start(span)
        return span

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
        yield self.start_span(name, context, kind, attributes, links, start_time, end_on_exit)


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


def handle_trace_response(resp):
    if resp.HasField("partial_success") and resp.partial_success:
        ps = resp.partial_success
        msg = f"partial success: rejected_spans: [{ps.rejected_spans}], error_message: [{ps.error_message}]"
        _logger.warning(msg)
