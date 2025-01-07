import logging
import threading
import time

from opentelemetry.sdk.trace.export import SpanExportResult
from oteltest import sink
from oteltest.sink.handler import AccumulatingHandler
from oteltest.telemetry import count_spans

from _lib import mk_span
from otelmini.trace import GrpcSpanExporter

_logger = logging.getLogger(__name__)


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


def test_exporter_w_server_unavailable():
    # by default max_retries=3 so it takes ~7s
    # attempt (1s) retry1 (2s) retry2 (4s) retry3
    exporter = GrpcSpanExporter()
    result = exporter.export([mk_span("my-span")])
    assert result == SpanExportResult.FAILURE


def test_exporter_w_server_initially_unavailable():
    handler = AccumulatingHandler()
    s = sink.GrpcSink(handler, _logger)

    def delay_start_sink():
        time.sleep(4)
        s.start()

    thread = threading.Thread(target=delay_start_sink)
    thread.start()

    exporter = GrpcSpanExporter()
    result = exporter.export([mk_span("my-span")])

    thread.join()

    assert result == SpanExportResult.SUCCESS
