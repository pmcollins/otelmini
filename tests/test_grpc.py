import logging
import threading
import time

import pytest
from opentelemetry.sdk.trace.export import SpanExportResult
from oteltest import sink
from oteltest.sink.handler import AccumulatingHandler
from oteltest.telemetry import count_spans

from _lib import mk_span
from otelmini.trace import GrpcSpanExporter

_logger = logging.getLogger(__name__)


@pytest.mark.slow
def test_exporter_single_grpc_request():
    # this test starts a grpc server and makes a request
    handler = AccumulatingHandler()
    s = sink.GrpcSink(handler, _logger)
    s.start()

    exporter = GrpcSpanExporter()
    exporter.export([mk_span("my-span")])
    exporter.shutdown()

    s.stop()

    assert count_spans(handler.telemetry) == 1


@pytest.mark.slow
def test_exporter_w_server_unavailable():
    # by default max_retries=3 so it takes ~7s
    # attempt (1s) retry1 (2s) retry2 (4s) retry3
    exporter = GrpcSpanExporter()
    result = exporter.export([mk_span("my-span")])
    assert result == SpanExportResult.FAILURE


@pytest.mark.slow
def test_exporter_w_server_initially_unavailable():
    client = ClientRunner()
    client.start()

    time.sleep(3)

    sink_runner = SinkRunner()
    sink_runner.start()

    result = client.stop()
    assert result == SpanExportResult.SUCCESS


class ClientRunner:

    def __init__(self):
        self.result = None
        self.client_thread = threading.Thread(target=self.run)

    def start(self):
        self.client_thread.start()

    def run(self):
        exporter = GrpcSpanExporter(max_retries=4)
        self.result = exporter.export([mk_span("my-span")])

    def stop(self):
        self.client_thread.join()
        return self.result


class SinkRunner:

    def __init__(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.handler = AccumulatingHandler()
        self.sink = sink.GrpcSink(self.handler, _logger)

    def start(self):
        self.thread.start()

    def _run(self):
        self.sink.start()
        self.sink.wait_for_termination()

    def get_telemetry(self):
        return self.handler.telemetry
