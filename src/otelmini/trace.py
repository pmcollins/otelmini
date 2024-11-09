import atexit
import queue
import threading
import time
import typing
from typing import Optional

from grpc import insecure_channel, RpcError
from opentelemetry.context import context
from opentelemetry.proto.collector.trace.v1.trace_service_pb2_grpc import TraceServiceStub
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from otelmini.encode import mk_trace_request


class Timer:

    def __init__(self, target_fcn, interval_seconds):
        self.thread = threading.Thread(target=self._target, daemon=True)
        self.target_fcn = target_fcn
        self.interval_seconds = interval_seconds
        self.sleeper = threading.Condition()
        self.stopper = threading.Event()

        # in effect, at python shutdown, we run the target one more time
        atexit.register(self._do_exit)

    def start(self):
        self.thread.start()

    def _target(self):
        while not self.stopper.is_set():
            self.target_fcn()
            with self.sleeper:
                self.sleeper.wait(self.interval_seconds)

    def _do_exit(self):
        self.stop()

    def notify_sleeper(self):
        with self.sleeper:
            self.sleeper.notify()

    def stop(self):
        self.stopper.set()
        self.notify_sleeper()

    def join(self):
        self.thread.join()


class ExponentialBackoff:

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
                    raise ExponentialBackoff.MaxAttemptsException(e)

    class MaxAttemptsException(Exception):

        def __init__(self, last_exception):
            super().__init__("Maximum retries reached")
            self.last_exception = last_exception


class OtlpGrpcExporter(SpanExporter):

    def __init__(self, logger, addr="127.0.0.1:4317", max_retries=4, client=None, sleep=time.sleep):
        self.logger = logger
        self.client = client if client is not None else TraceServiceStub(insecure_channel(addr))
        self.retrier = ExponentialBackoff(max_retries, logger, exceptions=(RpcError,), sleep=sleep)

    def export(self, spans: typing.Sequence[ReadableSpan]) -> SpanExportResult:
        request = mk_trace_request(spans)
        try:
            resp = self.retrier.retry(lambda: self.client.Export(request))
            self.logger.debug("export response: %s", resp)
            return SpanExportResult.SUCCESS
        except ExponentialBackoff.MaxAttemptsException as e:
            self.logger.warning("max retries reached: %s", e)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return False


class Batcher:

    def __init__(self, batch_size):
        self.lock = threading.RLock()
        self.batch_size = batch_size
        self.items = []

    def add(self, item):
        with self.lock:
            self.items.append(item)
            if len(self.items) == self.batch_size:
                out = self.items
                self.items = []
                return out
            return None

    def batch(self):
        with self.lock:
            out = self.items
            self.items = []
            return out


class BatchSpanProcessor(SpanProcessor):

    def __init__(self, exporter: SpanExporter, batch_size, interval_seconds, logger):
        self.exporter = exporter
        self.logger = logger
        self.batcher = Batcher(batch_size)
        self.batches = queue.Queue()
        self.stopper = threading.Event()

        self.timer = Timer(self._export, interval_seconds)
        self.timer.start()

    def on_start(self, span: Span, parent_context: Optional[context.Context] = None) -> None:
        self.logger.debug("on_start()")

    def on_end(self, span: ReadableSpan) -> None:
        self.logger.debug("on_end()")
        if not self.stopper.is_set():
            batch = self.batcher.add(span)
            if batch:
                self.logger.debug("enqueue batch and poke timer")
                self.batches.put(batch)
                self.timer.notify_sleeper()

    def _export(self):
        self.logger.debug("_export()")
        batch = self.batches.get()
        self.logger.debug("got batch from queue of len [%d]", len(batch))
        if batch is not None and len(batch) > 0:
            self.exporter.export(batch)

    def shutdown(self) -> None:
        self.logger.debug("shutdown")
        self.stopper.set()
        self.timer.stop()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        self.logger.debug("force_flush")
        return False
