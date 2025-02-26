from __future__ import annotations

import logging
import threading
import time
import typing
from typing import TYPE_CHECKING, Optional

from grpc import RpcError, insecure_channel
from opentelemetry import trace
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from otelmini._tracelib import Batcher, ExponentialBackoff, Timer, mk_trace_request

if TYPE_CHECKING:
    from opentelemetry.context import context

_tracer = trace.get_tracer(__name__)
_logger = logging.getLogger(__name__)


class GrpcSpanExporter(SpanExporter):
    def __init__(self, addr="127.0.0.1:4317", max_retries=3, channel_provider=None, sleep=time.sleep):
        self.channel_provider = channel_provider if channel_provider else lambda: insecure_channel(addr)
        self._connect()
        self.backoff = ExponentialBackoff(max_retries, exceptions=(RpcError,), sleep=sleep)

    def export(self, spans: typing.Sequence[ReadableSpan]) -> SpanExportResult:
        req = mk_trace_request(spans)
        try:
            resp = self.backoff.retry(SingleReqExporter(self, req).export)
            if resp.HasField("partial_success") and resp.partial_success:
                ps = resp.partial_success
                msg = f"partial success: rejected_spans: [{ps.rejected_spans}], error_message: [{ps.error_message}]"
                _logger.warning(msg)
            return SpanExportResult.SUCCESS  # noqa: TRY300
        except ExponentialBackoff.MaxAttemptsError:
            return SpanExportResult.FAILURE

    def export_single_request(self, req):
        try:
            return self.client.Export(req)
        except RpcError as e:
            # noinspection PyTypeChecker
            self._handle_export_failure(e)
            raise

    def _handle_export_failure(self, e):
        if hasattr(e, "code") and e.code:
            status = e.code().name  # e.g. "UNAVAILABLE"
            _logger.warning("Rpc error during export: %s", status)
        else:
            _logger.warning("Rpc error during export: %s", e)
        # close the channel, even if not strictly necessary
        self.shutdown()
        # if the export failed (e.g. because the server is unavailable) reconnect
        # otherwise later attempts will continue to fail even when the server comes back up
        self._connect()

    def _connect(self):
        self.channel = self.channel_provider()
        self.client = TraceServiceStub(self.channel)

    def shutdown(self) -> None:
        # causes no network transmission
        self.channel.close()

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        return False


class SingleReqExporter:
    def __init__(self, exporter, req):
        self.exporter = exporter
        self.req = req

    def export(self):
        return self.exporter.export_single_request(self.req)


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
