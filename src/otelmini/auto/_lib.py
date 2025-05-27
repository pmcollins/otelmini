import logging
import os
from typing import Optional

from opentelemetry import trace

from otelmini.log import BatchLogRecordProcessor, GrpcLogExporter, LoggerProvider, OtelBridgeLoggingHandler
from otelmini.processor import BatchProcessor
from otelmini.trace import GrpcSpanExporter, MiniTracerProvider

pylogger = logging.getLogger(__package__)
OTEL_MINI_LOG_FORMAT = "OTEL_MINI_LOG_FORMAT"


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
            pylogger.warning("Invalid integer value of '%s' for env var '%s'", val, key)
            return default

    def setval(self, key, value):
        self.store[key] = value

    def setdefault(self, key, value):
        self.store.setdefault(key, value)


class Config:

    def __init__(self, env: Env):
        self.log_format = env.getval(OTEL_MINI_LOG_FORMAT, logging.BASIC_FORMAT)

    def get_log_format(self):
        return self.log_format


class AutoInstrumentationManager:
    def __init__(self, env: Env):
        self.tracer_provider: Optional[MiniTracerProvider] = None
        self.logger_provider: Optional[LoggerProvider] = None
        self.otel_logging_handler: Optional[OtelBridgeLoggingHandler] = None
        self.root_logger: Optional[logging.Logger] = None
        self.config = Config(env)

    def set_up_tracing(self):
        self.tracer_provider = MiniTracerProvider(
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
        self.otel_logging_handler = OtelBridgeLoggingHandler(self.logger_provider)
        self.root_logger.addHandler(self.otel_logging_handler)

        self.set_up_console_logging()

    def set_up_console_logging(self):
        stream_handler = logging.StreamHandler()
        log_format = self.config.get_log_format()
        stream_handler.setFormatter(logging.Formatter(log_format))
        self.root_logger.addHandler(stream_handler)

    def shutdown(self):
        if self.tracer_provider:
            self.tracer_provider.shutdown()

        if self.logger_provider:
            self.logger_provider.shutdown()

        if self.otel_logging_handler and self.root_logger:
            self.root_logger.removeHandler(self.otel_logging_handler)
