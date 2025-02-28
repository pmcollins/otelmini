from __future__ import annotations

import logging
import threading
import time
import typing
from typing import TYPE_CHECKING, Optional, Sequence

from grpc import RpcError, insecure_channel
from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from otelmini._tracelib import Batcher, ExponentialBackoff, Timer, mk_trace_request
from otelmini.grpc import GrpcExporter, SingleReqExporter

if TYPE_CHECKING:
    from opentelemetry.context import context
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest, ExportTraceServiceResponse

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
            success_result=SpanExportResult.SUCCESS,
            failure_result=SpanExportResult.FAILURE
        )
    
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
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

    def on_start(self, span: Span, parent_context: Optional[context.Context] = None) -> None:
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
