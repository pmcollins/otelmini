import logging

import pytest
from oteltest import sink
from oteltest.sink.handler import AccumulatingHandler
from oteltest.telemetry import count_spans

from otelmini.trace import GrpcSpanExporter
from _lib import mk_span


@pytest.fixture
def logger():
    logging.basicConfig(level=logging.DEBUG)
    return logging.getLogger()


def test_exporter_single_grpc_request(logger):
    # this test starts a grpc server and makes a request
    handler = AccumulatingHandler()
    s = sink.GrpcSink(handler, logger)
    s.start()

    exporter = GrpcSpanExporter()
    exporter.export([mk_span("my-span")])
    exporter.shutdown()

    s.stop()

    assert count_spans(handler.telemetry) == 1


def test_exporter_w_server_unavailable(logger):
    exporter = GrpcSpanExporter()
    exporter.export([mk_span("my-span")])

