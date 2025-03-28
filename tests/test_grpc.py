import logging
import threading
import time

import pytest
from oteltest.sink import GrpcSink
from oteltest.sink.handler import AccumulatingHandler
from oteltest.telemetry import count_spans

from _lib import mk_span
from otelmini._lib import ExportResult
from otelmini.trace import GrpcSpanExporter

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

