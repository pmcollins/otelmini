import atexit
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

from otelmini.encode import mk_trace_request

tracer = trace.get_tracer(__name__)


class Timer:

    def __init__(self, target_fcn, interval_seconds, logger, daemon=True):
        self.thread = threading.Thread(target=self._target, daemon=daemon)
        self.target_fcn = target_fcn
        self.interval_seconds = interval_seconds
        self.logger = logger
        self.sleeper = threading.Condition()
        self.stopper = threading.Event()

        # TODO at python shutdown, run the target one more time
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
            self.logger.debug("sleeper wait start")
            self.sleeper.wait(self.interval_seconds)
            self.logger.debug("sleeper wait done")

    def notify_sleeper(self):
        with self.sleeper:
            self.sleeper.notify()

    def stop(self):
        self.stopper.set()
        self.notify_sleeper()
        self.target_fcn()

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


class GrpcExporter(SpanExporter):

    def __init__(self, logger, addr="127.0.0.1:4317", max_retries=4, client=None, sleep=time.sleep):
        self.logger = logger
        self.client = client if client is not None else TraceServiceStub(insecure_channel(addr))
        self.eb = ExponentialBackoff(max_retries, logger, exceptions=(RpcError,), sleep=sleep)

    def export(self, spans: typing.Sequence[ReadableSpan]) -> SpanExportResult:
        self.logger.debug("will export %d spans", len(spans))
        request = mk_trace_request(spans)
        try:
            resp = self.eb.retry(lambda: self.client.Export(request))
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


class BatchProcessor(SpanProcessor):

    def __init__(self, exporter: SpanExporter, batch_size, interval_seconds, logger, daemon=True):
        self.exporter = exporter
        self.logger = logger
        self.batcher = Batcher(batch_size)
        self.stopper = threading.Event()

        self.timer = Timer(self._export, interval_seconds, logger, daemon=daemon)
        self.timer.start()

    def on_start(self, span: Span, parent_context: Optional[context.Context] = None) -> None:
        self.logger.debug("on_start()")

    def on_end(self, span: ReadableSpan) -> None:
        self.logger.debug("on_end()")
        if not self.stopper.is_set():
            batched = self.batcher.add(span)
            if batched:
                self.logger.debug("enqueue batch and poke timer")
                self.timer.notify_sleeper()

    def _export(self):
        self.logger.debug("_export()")
        batch = self.batcher.pop()
        if batch is not None and len(batch) > 0:
            self.logger.debug("got batch from queue of len [%d]", len(batch))
            self.exporter.export(batch)

    def shutdown(self) -> None:
        self.logger.debug("shutdown")
        self.stopper.set()
        self.timer.stop()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        # todo implement
        self.logger.debug("force_flush")
        return False
