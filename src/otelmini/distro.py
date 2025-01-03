import logging

from opentelemetry import trace
from opentelemetry.instrumentation.distro import BaseDistro
from opentelemetry.sdk._configuration import _BaseConfigurator
from opentelemetry.sdk.trace import TracerProvider

from otelmini.trace import BatchProcessor, GrpcExporter


class OtelMiniDistro(BaseDistro):

    def _configure(self, **kwargs):
        logger = logging.getLogger("OtelMiniDistro")
        logger.info("configure running")


class OtelMiniConfigurator(_BaseConfigurator):

    def _configure(self, **kwargs):
        logger = logging.getLogger("OtelMiniConfigurator")
        logger.info("configure running")
        tracer_provider = TracerProvider()
        tracer_provider.add_span_processor(BatchProcessor(
            GrpcExporter(logging.getLogger("GrpcExporter")),
            batch_size=144,
            interval_seconds=12,
        ))
        trace.set_tracer_provider(tracer_provider)
