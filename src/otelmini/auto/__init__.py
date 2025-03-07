import logging
from dataclasses import dataclass
from typing import Optional

from opentelemetry import trace

from otelmini.log import BatchLogRecordProcessor, GrpcLogExporter, LoggerProvider, OtelBridgeHandler
from otelmini.processor import BatchProcessor
from otelmini.trace import GrpcSpanExporter, TracerProvider


@dataclass
class OtelMiniManager:
    """Manages the lifecycle of OpenTelemetry components."""
    tracer_provider: Optional[TracerProvider] = None
    logger_provider: Optional[LoggerProvider] = None
    otel_handler: Optional[OtelBridgeHandler] = None

    def shutdown(self):
        """Shut down all OpenTelemetry components."""
        if self.tracer_provider:
            self.tracer_provider.shutdown()
        
        if self.logger_provider:
            self.logger_provider.shutdown()
        
        if self.otel_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.otel_handler)


# Global instance to track OpenTelemetry components
manager = OtelMiniManager()


def set_up_tracing():
    """Set up OpenTelemetry tracing."""
    tracer_provider = TracerProvider(
        BatchProcessor(
            GrpcSpanExporter(),
            batch_size=144,
            interval_seconds=12,
        )
    )
    trace.set_tracer_provider(tracer_provider)
    manager.tracer_provider = tracer_provider


def set_up_logging(exporter=None):
    """Set up OpenTelemetry logging."""
    root_logger = logging.getLogger()
    if exporter is None:
        exporter = GrpcLogExporter()
    
    logger_provider = LoggerProvider([BatchLogRecordProcessor(exporter)])
    otel_handler = OtelBridgeHandler(logger_provider)
    
    root_logger.addHandler(otel_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    root_logger.addHandler(stream_handler)

    # Store references for shutdown
    manager.logger_provider = logger_provider
    manager.otel_handler = otel_handler
