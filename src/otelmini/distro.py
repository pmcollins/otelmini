import logging

from opentelemetry import trace
from opentelemetry.instrumentation.distro import BaseDistro
from opentelemetry.sdk._configuration import _BaseConfigurator
from opentelemetry.sdk.trace import TracerProvider

from otelmini.log import BatchLogRecordProcessor, ConsoleLogExporter, LoggerProvider, OtelBridgeHandler
from otelmini.trace import BatchProcessor, GrpcSpanExporter


class OtelMiniDistro(BaseDistro):
    def _configure(self, **kwargs):
        logger = logging.getLogger("OtelMiniDistro")
        logger.info("configure running")


class OtelMiniConfigurator(_BaseConfigurator):
    def _configure(self):
        logging.getLogger("OtelMiniConfigurator").info("configure running")

        set_up_tracing()
        set_up_logging()


def set_up_tracing():
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(
        BatchProcessor(
            GrpcSpanExporter(logging.getLogger("GrpcExporter")),
            batch_size=144,
            interval_seconds=12,
        )
    )
    trace.set_tracer_provider(tracer_provider)


def set_up_logging():
    logger_provider = LoggerProvider([(BatchLogRecordProcessor(ConsoleLogExporter()))])
    logging.getLogger().addHandler(OtelBridgeHandler(logger_provider))
