import logging
import typing

from opentelemetry import trace
from opentelemetry.trace import Tracer, TracerProvider
from opentelemetry.util import types

from otelmini.log import BatchLogRecordProcessor, ConsoleLogExporter, LoggerProvider, OtelBridgeHandler
from otelmini.trace import BatchProcessor, GrpcSpanExporter


class OtelMiniAutoInstrumentor:
    def configure(self):
        logging.getLogger(__name__).info("OtelMiniAutoInstrumentor configure running")
        set_up_tracing()
        set_up_logging()



def set_up_tracing():
    tracer_provider = MiniTracerProvider(BatchProcessor(
        GrpcSpanExporter(logging.getLogger("GrpcExporter")),
        batch_size=144,
        interval_seconds=12,
    ))
    trace.set_tracer_provider(tracer_provider)


def set_up_logging():
    logger_provider = LoggerProvider([(BatchLogRecordProcessor(ConsoleLogExporter()))])
    logging.getLogger().addHandler(OtelBridgeHandler(logger_provider))
