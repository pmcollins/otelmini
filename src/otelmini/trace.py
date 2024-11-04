import logging
import threading
import time
import typing
from typing import Optional

from grpc import RpcError, insecure_channel
from opentelemetry import trace
from opentelemetry.context import context
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from otelmini.encode import mk_trace_request


class ExecTimer:

    def __init__(self, target_fcn, interval_seconds, logger):
        self.target_fcn = target_fcn
        self.interval_seconds = interval_seconds
        self.logger = logger

        self.shutdown_event = threading.Event()
        self.lock = threading.RLock()

        self.tt = threading.Timer(self.interval_seconds, self._run_timer_target)

    def start(self):
        self.tt.start()

    def force_timeout(self, batch):
        self.logger.debug("force_timeout acquiring lock")
        with self.lock:
            self.logger.debug("force_timeout aquired lock, cancelling timer and starting a new 0s timer")
            self.tt.cancel()
            self.tt = self._mk_tt(0, batch)
            self.start()

    def shutdown(self):
        self.shutdown_event.set()

    def cancel(self):
        self.shutdown()
        self.tt.cancel()

    def _run_timer_target(self, target_fcn_arg):
        with self.lock:
            start_ns = time.time_ns()
            self.target_fcn(target_fcn_arg)
            execution_seconds = (time.time_ns() - start_ns) / 1e9
            self.logger.debug("target function took %.1fs", execution_seconds)
            if not self.shutdown_event.is_set():
                sleep_seconds = self._calc_sleep_seconds(execution_seconds)
                self.tt = self._mk_tt(sleep_seconds, None)
                self.start()

    def _mk_tt(self, interval_seconds, batch):
        self.logger.debug("creating %.1fs timer", interval_seconds)
        return threading.Timer(interval_seconds, self._run_timer_target, [batch])

    def _calc_sleep_seconds(self, execution_seconds):
        sleep_seconds = self.interval_seconds - execution_seconds
        if sleep_seconds <= 0:
            self.logger.debug(
                "execution time (%.1fs) was longer than interval (%.1fs)",
                execution_seconds,
                self.interval_seconds,
            )
            sleep_seconds = 0
        return sleep_seconds


class Retrier:
    class MaxAttemptsException(Exception):

        def __init__(self, last_exception):
            super().__init__("Maximum retries reached")
            self.last_exception = last_exception

    def __init__(self, max_attempts, logger, base_seconds=1, sleep=time.sleep, exceptions=(Exception,)):
        self.max_attempts = max_attempts
        self.logger = logger
        self.base_seconds = base_seconds
        self.sleep = sleep
        self.exceptions = exceptions

    def retry(self, func):
        for attempt in range(self.max_attempts):
            try:
                return func()
            except self.exceptions as e:
                if attempt < self.max_attempts - 1:
                    seconds = (2 ** attempt) * self.base_seconds
                    self.logger.debug("backing off for %d seconds", seconds)
                    self.sleep(seconds)
                else:
                    raise Retrier.MaxAttemptsException(e)


class OtlpGrpcExporter(SpanExporter):

    def __init__(self, logger, addr="127.0.0.1:4317", max_retries=4, client=None, sleep=time.sleep):
        self.logger = logger
        self.client = client if client is not None else TraceServiceStub(insecure_channel(addr))
        self.retrier = Retrier(max_retries, logger, exceptions=(RpcError,), sleep=sleep)

    def export(self, spans: typing.Sequence[ReadableSpan]) -> SpanExportResult:
        request = mk_trace_request(spans)
        try:
            resp = self.retrier.retry(lambda: self.client.Export(request))
            self.logger.debug("export response: %s", resp)
            return SpanExportResult.SUCCESS
        except Retrier.MaxAttemptsException as e:
            self.logger.warning("max retries reached: %s", e)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return False


class Accumulator:

    def __init__(self, batch_size):
        self.lock = threading.RLock()
        self.batch_size = batch_size
        self.spans = []

    def add(self, span):
        with self.lock:
            self.spans.append(span)
            if len(self.spans) == self.batch_size:
                out = self.spans
                self.spans = []
                return out
            return None

    def batch(self):
        with self.lock:
            out = self.spans
            self.spans = []
            return out


class BSP(SpanProcessor):

    def __init__(self, exporter: SpanExporter, batch_size, interval_seconds, logger):
        self.exporter = exporter
        self.logger = logger
        self.accumulator = Accumulator(batch_size)
        self.timer = ExecTimer(self._export, interval_seconds, logger)
        self.timer.start()

    def on_start(self, span: Span, parent_context: Optional[context.Context] = None) -> None:
        self.logger.debug("on start")

    def on_end(self, span: ReadableSpan) -> None:
        self.logger.debug("on end")
        batch = self.accumulator.add(span)
        if batch:
            self.timer.force_timeout(batch)

    def _export(self, batch):
        self.logger.debug("_export")
        if batch is None:
            self.logger.debug("batch arg is none, getting batch from accumulator")
            batch = self.accumulator.batch()
        if batch is not None:
            self.exporter.export(batch)

    def shutdown(self) -> None:
        self.logger.debug("shutdown")
        self.timer.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        self.logger.debug("force flush")
        return False


def otel():
    logging.basicConfig(level=logging.INFO)

    main_logger = logging.getLogger("main")

    tp = TracerProvider()
    exporter = OtlpGrpcExporter(logging.getLogger("FakeSpanExporter"))
    proc = BSP(exporter, batch_size=12, interval_seconds=4, logger=logging.getLogger("BSP"))
    tp.add_span_processor(proc)
    trace.set_tracer_provider(tp)

    tracer = tp.get_tracer("my-module")

    i = 0
    main_logger.info("12 spans")
    for _ in range(12):
        with tracer.start_span(f"span-{i}"):
            i += 1
            time.sleep(0.1)

    main_logger.info("sleep 6")
    time.sleep(6)

    main_logger.info("6 spans")
    for _ in range(6):
        with tracer.start_span(f"span-{i}"):
            i += 1
            time.sleep(0.1)

    tp.shutdown()


if __name__ == '__main__':
    otel()
