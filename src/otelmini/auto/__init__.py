import logging

from opentelemetry import trace

from otelmini.log import BatchLogRecordProcessor, GrpcLogExporter, LoggerProvider, OtelBridgeHandler
from otelmini.processor import BatchProcessor
from otelmini.trace import GrpcSpanExporter, TracerProvider


def set_up_tracing():
    tracer_provider = TracerProvider(
        BatchProcessor(
            GrpcSpanExporter(),
            batch_size=144,
            interval_seconds=12,
        )
    )
    trace.set_tracer_provider(tracer_provider)


def set_up_logging():
    root_logger = logging.getLogger()
    root_logger.addHandler(OtelBridgeHandler(LoggerProvider([(BatchLogRecordProcessor(GrpcLogExporter()))])))

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    root_logger.addHandler(stream_handler)
