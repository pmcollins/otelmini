from __future__ import annotations

import logging
import threading
import time
import typing
from typing import Iterator, Optional, Sequence

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
from opentelemetry.trace import _Links, SpanKind, Tracer, TracerProvider
from opentelemetry.util import types

from otelmini._tracelib import Batcher, MiniSpan, mk_trace_request, Timer
from otelmini.grpc import GrpcExporter

_tracer = trace.get_tracer(__name__)
_logger = logging.getLogger(__name__)


def handle_trace_response(resp):
    """
    Handle the response from the gRPC endpoint for traces.
    
    Args:
        resp: The response from the gRPC endpoint
    """
    if resp.HasField("partial_success") and resp.partial_success:
        ps = resp.partial_success
        msg = f"partial success: rejected_spans: [{ps.rejected_spans}], error_message: [{ps.error_message}]"
        _logger.warning(msg)


class Span:
    pass


class SpanProcessor:
    pass


class SpanExporter:
    pass


class SpanExportResult:
    pass


class MiniTracer(Tracer):

    def start_span(
        self, name: str,
        context: Optional[Context] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: types.Attributes = None,
        links: _Links = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True
    ) -> Span:
        pass

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
    ) -> Iterator["Span"]:
        pass


class MiniTracerProvider(TracerProvider):

    def __init__(self, span_processor=None):
        self.span_processor = span_processor

    def get_tracer(
        self, instrumenting_module_name: str,
        instrumenting_library_version: typing.Optional[str] = None,
        schema_url: typing.Optional[str] = None,
        attributes: typing.Optional[types.Attributes] = None,
    ) -> Tracer:
        return MiniTracer()


class GrpcSpanExporter(SpanExporter):
    """
    A gRPC exporter for spans that uses composition with the generic GrpcExporter.
    """

    def __init__(self, addr="127.0.0.1:4317", max_retries=3, channel_provider=None, sleep=time.sleep):
        """
        Initialize the gRPC span exporter.
        
        Args:
            addr: The address of the gRPC endpoint
            max_retries: Maximum number of retry attempts
            channel_provider: A function that returns a gRPC channel
            sleep: A function used for sleeping between retries
        """
        self._exporter = GrpcExporter(
            addr=addr,
            max_retries=max_retries,
            channel_provider=channel_provider,
            sleep=sleep,
            stub_class=TraceServiceStub,
            response_handler=handle_trace_response,
        )

    def export(self, spans: Sequence[MiniSpan]) -> SpanExportResult:
        """
        Export spans to the gRPC endpoint.
        
        Args:
            spans: The spans to export
            
        Returns:
            The result of the export operation
        """
        req = mk_trace_request(spans)
        return self._exporter.export_request(req)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """
        Force flush any pending exports.
        
        Args:
            timeout_millis: The timeout in milliseconds
            
        Returns:
            Whether the flush was successful
        """
        return self._exporter.force_flush(timeout_millis)

    def shutdown(self) -> None:
        """
        Shutdown the exporter.
        """
        self._exporter.shutdown()


class BatchProcessor(SpanProcessor):
    def __init__(self, exporter: SpanExporter, batch_size, interval_seconds):
        self.exporter = exporter
        self.batcher = Batcher(batch_size)
        self.stopper = threading.Event()

        self.timer = Timer(self._export, interval_seconds)
        self.timer.start()

    def on_start(self, span: Span) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
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
