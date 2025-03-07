import logging
import os
from typing import Optional

from opentelemetry import trace

from otelmini.log import BatchLogRecordProcessor, GrpcLogExporter, LoggerProvider, OtelBridgeHandler
from otelmini.processor import BatchProcessor
from otelmini.trace import GrpcSpanExporter, TracerProvider

_pylogger = logging.getLogger(__package__)


class Env:
    """
    Wrapper around a system's environment variables with convenience methods.
    Defaults to using os.environ but you can pass in a dictionary for testing.
    """

    def __init__(self, store=None):
        self.store = os.environ if store is None else store

    def is_true(self, key, default=""):
        s = self.getval(key, default)
        return s.strip().lower() == "true"

    def list_append(self, key, value):
        curr = self.getval(key)
        if curr:
            curr += ","
        self.setval(key, curr + value)

    def getval(self, key, default=""):
        return self.store.get(key, default)

    def getint(self, key, default=0):
        val = self.getval(key, str(default))
        try:
            return int(val)
        except ValueError:
            _pylogger.warning("Invalid integer value of '%s' for env var '%s'", val, key)
            return default

    def setval(self, key, value):
        self.store[key] = value

    def setdefault(self, key, value):
        self.store.setdefault(key, value)


class OtelMiniManager:
    """Manages the lifecycle of OpenTelemetry components."""

    def __init__(self):
        self.tracer_provider: Optional[TracerProvider] = None
        self.logger_provider: Optional[LoggerProvider] = None
        self.otel_handler: Optional[OtelBridgeHandler] = None
        self.root_logger: Optional[logging.Logger] = None

    def set_up_tracing(self):
        self.tracer_provider = TracerProvider(
            BatchProcessor(
                GrpcSpanExporter(),
                batch_size=144,
                interval_seconds=12,
            )
        )
        trace.set_tracer_provider(self.tracer_provider)

    def set_up_logging(self, exporter=None):
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
