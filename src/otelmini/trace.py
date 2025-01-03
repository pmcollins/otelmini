import threading
import time
import typing
from typing import Optional

from grpc import insecure_channel, RpcError
from opentelemetry import trace
from opentelemetry.context import context
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from otelmini._tracelib import Batcher, ExponentialBackoff, Timer, mk_trace_request

_tracer = trace.get_tracer(__name__)


class GrpcExporter(SpanExporter):

    def __init__(self, addr="127.0.0.1:4317", max_retries=4, client=None, sleep=time.sleep):
        self.client = client if client is not None else TraceServiceStub(insecure_channel(addr))
        self.backoff = ExponentialBackoff(max_retries, exceptions=(RpcError,), sleep=sleep)

    def export(self, spans: typing.Sequence[ReadableSpan]) -> SpanExportResult:
        request = mk_trace_request(spans)
        try:
            resp = self.backoff.retry(lambda: self.client.Export(request))
            if resp.HasField("partial_success"):
                ps = resp.partial_success
                print(f"partial success: rejected_spans: [{ps.rejected_spans}], error_message: [{ps.error_message}]")
            return SpanExportResult.SUCCESS
        except ExponentialBackoff.MaxAttemptsException:
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return False


class BatchProcessor(SpanProcessor):

    def __init__(self, exporter: SpanExporter, batch_size, interval_seconds, daemon=True):
        self.exporter = exporter
        self.batcher = Batcher(batch_size)
        self.stopper = threading.Event()

        self.timer = Timer(self._export, interval_seconds, daemon=daemon)
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

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        # todo implement
        return False
