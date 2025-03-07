import logging
import threading
import time

import pytest
from oteltest import sink as sink_lib
from oteltest.sink import GrpcSink
from oteltest.sink.handler import AccumulatingHandler
from oteltest.telemetry import count_spans

from _lib import mk_span
from otelmini.grpc import GrpcExportResult
from otelmini.trace import GrpcSpanExporter

# run e.g. `pytest --log-cli-level=INFO`
# to see log statements during tests
_logger = logging.getLogger(__package__)


# `pytest -m "not slow"` to skip these
@pytest.mark.slow
def test_exporter_single_grpc_request():
    handler = AccumulatingHandler()
    sink = GrpcSink(handler, _logger)
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
    assert result == GrpcExportResult.FAILURE


@pytest.mark.slow
def test_exporter_w_server_initially_unavailable():
    export = ExportAsyncRunner()
    export.start()

    time.sleep(3)

    sink = SinkAsyncRunner()
    sink.start()

    result = export.wait_for_result()
    assert result == GrpcExportResult.SUCCESS

    sink.stop()


@pytest.mark.slow
def test_exporter_w_alternating_server_availability():
    _logger.info("Sink ON")
    sink_runner = SinkAsyncRunner()
    sink_runner.start()

    time.sleep(1)

    _logger.info("Export")
    export_runner = ExportAsyncRunner()
    export_runner.start()
    result = export_runner.wait_for_result()
    _logger.info(f"Expect success: {result}")
    assert result == GrpcExportResult.SUCCESS

    sink_runner.stop()
    _logger.info("Sink OFF")
    time.sleep(1)

    _logger.info("Export")
    export_runner = ExportAsyncRunner()
    export_runner.start()
    result = export_runner.wait_for_result()
    _logger.info(f"Expect failure: {result}")
    assert result == GrpcExportResult.FAILURE

    _logger.info("Start export with sink OFF")
    export_runner = ExportAsyncRunner()
    export_runner.start()

    time.sleep(5)

    _logger.info("Sink ON after sleep")
    sink_runner = SinkAsyncRunner()
    sink_runner.start()

    result = export_runner.wait_for_result()
    _logger.info(f"Expect success: {result}")
    assert result == GrpcExportResult.SUCCESS

    sink_runner.stop()
    _logger.info("Sink OFF")


class ExportAsyncRunner:

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


class SinkAsyncRunner:

    def __init__(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.handler = AccumulatingHandler()
        self.sink = sink_lib.GrpcSink(self.handler, _logger)

    def start(self):
        self.thread.start()

    def _run(self):
        self.sink.start()
        self.sink.wait_for_termination()

    def get_telemetry(self):
        return self.handler.telemetry

    def stop(self):
        self.sink.stop()
        self.thread.join()
