import time
import pickle

import pytest
from _lib import mk_span
from grpc import RpcError, StatusCode
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from otelmini._lib import ExponentialBackoff, ExportResult
from otelmini._grpclib import GrpcExporter
from otelmini.processor import Timer
from otelmini.trace import GrpcSpanExporter, MiniSpan, Resource, InstrumentationScope, SpanContext


def test_stubborn_runner():
    runner = StubbornRunner(1, lambda: "hello")
    with pytest.raises(Exception):
        runner.attempt()
    assert runner.attempt() == "hello"


def test_backoff_eventual_success():
    greeter = StubbornRunner(2, lambda: "hello")
    f = FakeSleeper()
    backoff = ExponentialBackoff(max_retries=2, sleep=f.sleep)
    assert backoff.retry(lambda: greeter.attempt()) == "hello"
    assert f.sleeps == [1, 2]


def test_backoff_eventual_failure():
    backoff = ExponentialBackoff(max_retries=1, sleep=FakeSleeper().sleep)
    with pytest.raises(ExponentialBackoff.MaxAttemptsError):
        greeter = StubbornRunner(2, lambda: "hello")
        backoff.retry(lambda: greeter.attempt())


def test_backoff_abort_retry():
    def abort_retry(e: RpcError):
        if hasattr(e, "code") and e.code:
            return e.code() != StatusCode.UNAVAILABLE
        return True

    def my_function():
        raise RpcError()

    backoff = ExponentialBackoff(max_retries=1, sleep=FakeSleeper().sleep, abort_retry=abort_retry)
    backoff.retry(my_function)


def test_faked_exporter_with_retry_then_success():
    sleeper = FakeSleeper()
    channel = FakeChannel(3)
    exporter = GrpcSpanExporter(channel_provider=lambda: channel, sleep=sleeper.sleep)
    spans = [mk_span("my-span")]
    resp = exporter.export(spans)
    assert resp == ExportResult.SUCCESS
    assert len(channel.export_requests) == 4


def test_faked_exporter_with_retry_failure():
    sleeper = FakeSleeper()
    channel = FakeChannel(4)
    exporter = GrpcSpanExporter(channel_provider=lambda: channel, sleep=sleeper.sleep)
    spans = [mk_span("my-span")]
    resp = exporter.export(spans)
    assert resp == ExportResult.FAILURE
    assert len(channel.export_requests) == 4


def disabled_test_span_exporter_pickleable():
    exporter = GrpcSpanExporter(
        addr="localhost:4317",
        max_retries=5
    )

    pickled = pickle.dumps(exporter)
    unpickled = pickle.loads(pickled)

    assert unpickled.addr == "localhost:4317"
    assert unpickled.max_retries == 5

    unpickled.shutdown()


def test_span_dict_serialization():
    span = MiniSpan(
        name="test",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None
    )

    span_dict = span.to_dict()
    new_span = MiniSpan.from_dict(span_dict, on_end_callback=lambda s: None)

    assert new_span.get_name() == "test"
    assert new_span.get_span_context().trace_id == 1
    assert new_span.get_span_context().span_id == 2


class FakeChannel:

    def __init__(self, failed_attempts_before_success):
        self.failed_attempts_before_success = failed_attempts_before_success
        self.attempts = 0
        self.export_requests = []

    def unary_unary(self, *args, **kwargs):
        def export_func(req: ExportTraceServiceRequest):
            self.export_requests.append(req)
            self.attempts += 1
            if self.attempts <= self.failed_attempts_before_success:
                raise RpcError()
            return ExportTraceServiceResponse()

        return export_func

    def close(self):
        pass


class FakeSleeper:

    def __init__(self):
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)


class StubbornRunner:
    """For testing Retrier"""

    def __init__(self, num_failures_before_success, func, exception=Exception()):
        self.i = 0
        self.num_failures_before_success = num_failures_before_success
        self.func = func
        self.exception = exception

    def attempt(self):
        self.i += 1
        if self.i <= self.num_failures_before_success:
            raise self.exception
        return self.func()
