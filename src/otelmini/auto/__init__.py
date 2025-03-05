import logging

from opentelemetry import trace

from otelmini.log import BatchLogRecordProcessor, ConsoleLogExporter, LoggerProvider, OtelBridgeHandler
from otelmini.processor import BatchProcessor
from otelmini.trace import GrpcSpanExporter, TracerProvider


def set_up_tracing():
    tracer_provider = TracerProvider(BatchProcessor(
        GrpcSpanExporter(),
        batch_size=144,
        interval_seconds=12,
    ))
    trace.set_tracer_provider(tracer_provider)


def set_up_logging():
    logger_provider = LoggerProvider([(BatchLogRecordProcessor(ConsoleLogExporter()))])
    logging.getLogger().addHandler(OtelBridgeHandler(logger_provider))
