import logging
from importlib.metadata import entry_points
from typing import Optional

from opentelemetry import metrics, trace

from otelmini.env import Config
from otelmini.log import (
    HttpLogExporter,
    LoggerProvider,
    OtelBridgeLoggingHandler,
)
from otelmini.metric import (
    HttpMetricExporter,
    MeterProvider,
    PeriodicExportingMetricReader,
)
from otelmini.processor import BatchProcessor
from otelmini.trace import HttpSpanExporter, MiniTracerProvider

_logger = logging.getLogger(__name__)


def _get_endpoint(config: Config, signal: str) -> str:
    """Get endpoint for a signal, using signal-specific override if set."""
    override = getattr(config, f"exporter_{signal}_endpoint")
    if override:
        return override
    return f"{config.exporter_endpoint}/v1/{signal}"


def _discover_instrumentors():
    """Discover and activate all installed OpenTelemetry instrumentors."""
    for ep in entry_points(group="opentelemetry_instrumentor"):
        try:
            instrumentor_cls = ep.load()
            instrumentor = instrumentor_cls()
            if not instrumentor.is_instrumented_by_opentelemetry:
                instrumentor.instrument()
                _logger.debug("Instrumented %s", ep.name)
        except Exception as e:
            _logger.debug("Failed to instrument %s: %s", ep.name, e)


class Tracing:
    def __init__(self, config: Config):
        self.config = config
        self.provider: Optional[MiniTracerProvider] = None

    def set_up(self):
        self.provider = MiniTracerProvider(
            BatchProcessor(
                HttpSpanExporter(endpoint=_get_endpoint(self.config, "traces")),
                batch_size=self.config.bsp_batch_size,
                interval_seconds=self.config.bsp_schedule_delay_ms / 1000,
            ),
            config=self.config,
        )
        trace.set_tracer_provider(self.provider)

    def shutdown(self):
        if self.provider:
            self.provider.shutdown()


class Metrics:
    def __init__(self, config: Config):
        self.config = config
        self.provider: Optional[MeterProvider] = None

    def set_up(self):
        reader = PeriodicExportingMetricReader(
            HttpMetricExporter(endpoint=_get_endpoint(self.config, "metrics")),
            export_interval_millis=self.config.metric_export_interval_ms,
        )
        self.provider = MeterProvider(metric_readers=(reader,), config=self.config)
        metrics.set_meter_provider(self.provider)

    def shutdown(self):
        if self.provider:
            self.provider.shutdown()


class Logging:
    def __init__(self, config: Config):
        self.config = config
        self.provider: Optional[LoggerProvider] = None
        self.handler: Optional[OtelBridgeLoggingHandler] = None
        self.root_logger: Optional[logging.Logger] = None

    def set_up(self):
        self.root_logger = logging.getLogger()
        self.provider = LoggerProvider(
            BatchProcessor(
                HttpLogExporter(endpoint=_get_endpoint(self.config, "logs")),
                batch_size=self.config.bsp_batch_size,
                interval_seconds=self.config.bsp_schedule_delay_ms / 1000,
            ),
            config=self.config,
        )
        self.handler = OtelBridgeLoggingHandler(self.provider)
        self.root_logger.addHandler(self.handler)
        self._set_up_console()

    def _set_up_console(self):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(self.config.mini_log_format))
        self.root_logger.addHandler(stream_handler)

    def shutdown(self):
        if self.provider:
            self.provider.shutdown()
        if self.handler and self.root_logger:
            self.root_logger.removeHandler(self.handler)


class AutoInstrumentation:
    """Coordinates setup of tracing, metrics, and logging for auto-instrumentation."""

    def __init__(self, config: Config):
        self.config = config
        self.tracing = Tracing(config)
        self.metrics = Metrics(config)
        self.logging = Logging(config)

    def set_up_tracing(self):
        self.tracing.set_up()

    def set_up_metrics(self):
        self.metrics.set_up()

    def set_up_logging(self):
        self.logging.set_up()

    def instrument_libraries(self):
        _discover_instrumentors()

    def shutdown(self):
        self.tracing.shutdown()
        self.logging.shutdown()
        self.metrics.shutdown()
