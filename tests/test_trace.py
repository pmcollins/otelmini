import logging
import time

import pytest
from grpc import RpcError
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from opentelemetry.trace import SpanContext
from oteltest import sink
from oteltest.private import AccumulatingHandler
from oteltest.telemetry import count_spans

from otelmini.trace import GrpcExporter
from otelmini._tracelib import ExponentialBackoff, Timer


@pytest.fixture
def logger():
    logging.basicConfig(level=logging.DEBUG)
    return logging.getLogger()


def test_single_grpc_request(logger):
    # this test starts a grpc server and makes a request
    handler = AccumulatingHandler()
    s = sink.GrpcSink(handler, logger)
    s.start()

    exporter = GrpcExporter()
    spans = [mk_span("my-span")]
    exporter.export(spans)

    s.stop()

    assert count_spans(handler.telemetry) == 1


def test_eventual_runner():
    runner = EventualRunner(1, lambda: "hello")
    with pytest.raises(Exception):
        runner.attempt()
    assert runner.attempt() == "hello"


def test_retrier_eventual_success():
    greeter = EventualRunner(2, lambda: "hello")
    f = FakeSleeper()
    retrier = ExponentialBackoff(max_attempts=3, sleep=f.sleep)
    assert retrier.retry(lambda: greeter.attempt()) == "hello"
    assert f.sleeps == [1, 2]


def test_retrier_eventual_failure():
    retrier = ExponentialBackoff(max_attempts=2, sleep=FakeSleeper().sleep)
    with pytest.raises(ExponentialBackoff.MaxAttemptsException):
        greeter = EventualRunner(2, lambda: "hello")
        retrier.retry(lambda: greeter.attempt())


def test_faked_exporter_with_retry_then_success():
    sleeper = FakeSleeper()
    exporter = GrpcExporter(client=FakeGrpcClient(3), sleep=sleeper.sleep)
    spans = [mk_span("my-span")]
    resp = exporter.export(spans)
    assert resp == SpanExportResult.SUCCESS


def test_faked_exporter_with_retry_failure():
    sleeper = FakeSleeper()
    exporter = GrpcExporter(client=FakeGrpcClient(4), sleep=sleeper.sleep)
    spans = [mk_span("my-span")]
    resp = exporter.export(spans)
    assert resp == SpanExportResult.FAILURE


def test_timer():
    mylist = []
    t = Timer(lambda: mylist.append("x"), 144)
    t.start()
    for i in range(6):
        t.notify_sleeper()
        time.sleep(0.0001)
    assert len(mylist) == 6


def mk_span(name):
    return ReadableSpan(name, context=SpanContext(0, 0, False))


class FakeGrpcClient:

    def __init__(self, failed_attempts_before_success):
        self.failed_attempts_before_success = failed_attempts_before_success
        self.attempts = 0

    def Export(self, request):
        self.attempts += 1
        if self.attempts <= self.failed_attempts_before_success:
            raise RpcError()
        return ExportTraceServiceResponse()


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
