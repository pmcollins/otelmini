import time

import pytest
from _lib import mk_span
from grpc import RpcError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)

from otelmini._tracelib import ExponentialBackoff
from otelmini.grpc import GrpcExportResult
from otelmini.trace import GrpcSpanExporter, Timer


def test_eventual_runner():
    runner = EventualRunner(1, lambda: "hello")
    with pytest.raises(Exception):
        runner.attempt()
    assert runner.attempt() == "hello"


def test_retrier_eventual_success():
    greeter = EventualRunner(2, lambda: "hello")
    f = FakeSleeper()
    retrier = ExponentialBackoff(max_retries=2, sleep=f.sleep)
    assert retrier.retry(lambda: greeter.attempt()) == "hello"
    assert f.sleeps == [1, 2]


def test_retrier_eventual_failure():
    retrier = ExponentialBackoff(max_retries=1, sleep=FakeSleeper().sleep)
    with pytest.raises(ExponentialBackoff.MaxAttemptsError):
        greeter = EventualRunner(2, lambda: "hello")
        retrier.retry(lambda: greeter.attempt())


def test_faked_exporter_with_retry_then_success():
    sleeper = FakeSleeper()
    channel = FakeChannel(3)
    exporter = GrpcSpanExporter(channel_provider=lambda: channel, sleep=sleeper.sleep)
    spans = [mk_span("my-span")]
    resp = exporter.export(spans)
    assert resp == GrpcExportResult.SUCCESS
    assert len(channel.export_requests) == 4


def test_faked_exporter_with_retry_failure():
    sleeper = FakeSleeper()
    channel = FakeChannel(4)
    exporter = GrpcSpanExporter(channel_provider=lambda: channel, sleep=sleeper.sleep)
    spans = [mk_span("my-span")]
    resp = exporter.export(spans)
    assert resp == GrpcExportResult.FAILURE
    assert len(channel.export_requests) == 4


def test_timer():
    mylist = []
    t = Timer(lambda: mylist.append("x"), 144)
    t.start()
    for i in range(6):
        t.notify_sleeper()
        time.sleep(0.0001)
    assert len(mylist) == 6


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


class EventualRunner:
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
