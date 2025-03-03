import logging
import typing
from abc import ABC

from opentelemetry import trace
from opentelemetry.trace import Tracer, TracerProvider
from opentelemetry.util import types

from otelmini.log import BatchLogRecordProcessor, ConsoleLogExporter, LoggerProvider, OtelBridgeHandler
from otelmini.trace import BatchProcessor, GrpcSpanExporter


class Configurator(ABC):
    def configure(self, **kwargs):
        pass


class OtelMiniDistro(Configurator):
    def configure(self, **kwargs):
        logger = logging.getLogger("OtelMiniDistro")
        logger.info("configure running")


class OtelMiniConfigurator(Configurator):
    def configure(self):
        logging.getLogger("OtelMiniConfigurator").info("configure running")

        set_up_tracing()
        set_up_logging()


class MiniTracerProvider(TracerProvider):

    def __init__(self, span_processor=None):
        self.span_processor = span_processor

    def get_tracer(
        self, instrumenting_module_name: str,
        instrumenting_library_version: typing.Optional[str] = None,
        schema_url: typing.Optional[str] = None,
        attributes: typing.Optional[types.Attributes] = None,
    ) -> Tracer:
        pass


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
