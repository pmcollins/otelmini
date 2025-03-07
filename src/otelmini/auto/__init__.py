import logging
from typing import Optional

from opentelemetry import trace

from otelmini.log import BatchLogRecordProcessor, GrpcLogExporter, LoggerProvider, OtelBridgeHandler
from otelmini.processor import BatchProcessor
from otelmini.trace import GrpcSpanExporter, TracerProvider


class OtelMiniManager:
    """Manages the lifecycle of OpenTelemetry components."""

    def __init__(self):
        self.tracer_provider: Optional[TracerProvider] = None
        self.logger_provider: Optional[LoggerProvider] = None
        self.otel_handler: Optional[OtelBridgeHandler] = None
        self.root_logger: Optional[logging.Logger] = None

    def set_up_tracing(self):
        """Set up OpenTelemetry tracing."""
        self.tracer_provider = TracerProvider(
            BatchProcessor(
                GrpcSpanExporter(),
                batch_size=144,
                interval_seconds=12,
            )
        )
        trace.set_tracer_provider(self.tracer_provider)

    def set_up_logging(self, exporter=None):
        """Set up OpenTelemetry logging."""
        self.root_logger = logging.getLogger()
        if exporter is None:
            exporter = GrpcLogExporter()

        self.logger_provider = LoggerProvider([BatchLogRecordProcessor(exporter)])
        self.otel_handler = OtelBridgeHandler(self.logger_provider)
        self.root_logger.addHandler(self.otel_handler)

        self.set_up_console_logging()

    def set_up_console_logging(self):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
        self.root_logger.addHandler(stream_handler)

    def shutdown(self):
        """Shut down all OpenTelemetry components."""
        if self.tracer_provider:
            self.tracer_provider.shutdown()

        if self.logger_provider:
            self.logger_provider.shutdown()

        if self.otel_handler and self.root_logger:
            self.root_logger.removeHandler(self.otel_handler)


# Global instance to track OpenTelemetry components
manager = OtelMiniManager()


# Convenience functions that delegate to the global manager
def set_up_tracing():
    manager.set_up_tracing()


def set_up_logging(exporter=None):
    manager.set_up_logging(exporter)
