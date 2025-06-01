import logging
import pickle
import threading
import time

import pytest
from grpc import RpcError, StatusCode
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest, \
    ExportTraceServiceResponse
from oteltest.sink import GrpcSink
from oteltest.sink.handler import AccumulatingHandler
from oteltest.telemetry import count_spans

from otelmini._lib import ExportResult, Retrier
from otelmini.trace import GrpcSpanExporter
from tests._lib import mk_span, FakeSleeper, StubbornRunner

# run e.g. `pytest --log-cli-level=INFO`
# to see log statements during tests
logger = logging.getLogger(__name__)


# `pytest -m "not slow"` to skip these
@pytest.mark.slow
def test_exporter_single_grpc_request():
    handler = AccumulatingHandler()
    sink = GrpcSink(handler, logger)
    sink.start()

    exporter = GrpcSpanExporter()
    exporter.export([mk_span("my-span")])
    exporter.shutdown()

    assert count_spans(handler.telemetry) == 1

    sink.stop()


@pytest.mark.slow
def test_exporter_w_server_unavailable():
    # by default max_retries=3 so it takes ~7s
    # attempt (1s) retry1 (2s) retry2 (4s) retry3
    exporter = GrpcSpanExporter()
    result = exporter.export([mk_span("my-span")])
    assert result == ExportResult.FAILURE


@pytest.mark.slow
def test_exporter_w_server_initially_unavailable():
    export = SingleExportAsyncRunner()
    export.start()

    time.sleep(3)

    handler = AccumulatingHandler()
    sink = GrpcSink(handler, logger)
    sink.start()

    result = export.wait_for_result()
    assert result == ExportResult.SUCCESS

    sink.stop()


@pytest.mark.slow
def test_exporter_w_alternating_server_availability():
    logger.info("Sink ON")
    handler = AccumulatingHandler()
    sink = GrpcSink(handler, logger)
    sink.start()

    time.sleep(1)

    logger.info("Export")
    export_runner = SingleExportAsyncRunner()
    export_runner.start()
    result = export_runner.wait_for_result()
    logger.info(f"Expect success: {result}")
    assert result == ExportResult.SUCCESS

    sink.stop()
    logger.info("Sink OFF")
    time.sleep(1)

    logger.info("Export")
    export_runner = SingleExportAsyncRunner()
    export_runner.start()
    result = export_runner.wait_for_result()
    logger.info(f"Expect failure: {result}")
    assert result == ExportResult.FAILURE

    logger.info("Start export with sink OFF")
    export_runner = SingleExportAsyncRunner()
    export_runner.start()

    time.sleep(5)

    logger.info("Sink ON after sleep")
    handler = AccumulatingHandler()
    sink = GrpcSink(handler, logger)
    sink.start()

    result = export_runner.wait_for_result()
    logger.info(f"Expect success: {result}")
    assert result == ExportResult.SUCCESS
    assert count_spans(handler.telemetry) == 1

    sink.stop()
    logger.info("Sink OFF")


def test_backoff_should_retry():
    sleeper = FakeSleeper()
    retrier = Retrier(max_retries=2, sleep=sleeper.sleep)

    r = StubbornRunner(1, lambda: print("request"))
    retrier.retry(r.attempt)
    assert sleeper.sleeps == [1]


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
                raise FakeRpcError(StatusCode.UNAVAILABLE)
            return ExportTraceServiceResponse()

        return export_func

    def close(self):
        pass


class SingleExportAsyncRunner:
    def __init__(self):
        self.result = None
        self.thread = threading.Thread(target=self._run)

    def start(self):
        self.thread.start()

    def _run(self):
        exporter = GrpcSpanExporter(max_retries=4)
        self.result = exporter.export([mk_span("my-span")])

    def wait_for_result(self):
        self.thread.join()
        return self.result


class FakeRpcError(RpcError):
    def __init__(self, status_code):
        self.status_code = status_code

    def code(self):
        return self.status_code
