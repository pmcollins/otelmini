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


class AutoInstrumentationManager:
    def __init__(self, config: Config):
        self.config = config
        self.tracer_provider: Optional[MiniTracerProvider] = None
        self.logger_provider: Optional[LoggerProvider] = None
        self.meter_provider: Optional[MeterProvider] = None
        self.otel_logging_handler: Optional[OtelBridgeLoggingHandler] = None
        self.root_logger: Optional[logging.Logger] = None

    def _get_traces_endpoint(self) -> str:
        if self.config.exporter_traces_endpoint:
            return self.config.exporter_traces_endpoint
        return f"{self.config.exporter_endpoint}/v1/traces"

    def _get_metrics_endpoint(self) -> str:
        if self.config.exporter_metrics_endpoint:
            return self.config.exporter_metrics_endpoint
        return f"{self.config.exporter_endpoint}/v1/metrics"

    def _get_logs_endpoint(self) -> str:
        if self.config.exporter_logs_endpoint:
            return self.config.exporter_logs_endpoint
        return f"{self.config.exporter_endpoint}/v1/logs"

    def set_up_tracing(self):
        self.tracer_provider = MiniTracerProvider(
            BatchProcessor(
                HttpSpanExporter(endpoint=self._get_traces_endpoint()),
                batch_size=self.config.bsp_batch_size,
                interval_seconds=self.config.bsp_schedule_delay_ms / 1000,
            ),
            config=self.config,
        )
        trace.set_tracer_provider(self.tracer_provider)

    def set_up_metrics(self):
        reader = PeriodicExportingMetricReader(
            HttpMetricExporter(endpoint=self._get_metrics_endpoint()),
            export_interval_millis=self.config.metric_export_interval_ms,
        )
        self.meter_provider = MeterProvider(metric_readers=(reader,), config=self.config)
        metrics.set_meter_provider(self.meter_provider)

    def set_up_logging(self):
        self.root_logger = logging.getLogger()
        self.logger_provider = LoggerProvider(
            BatchProcessor(
                HttpLogExporter(endpoint=self._get_logs_endpoint()),
                batch_size=self.config.bsp_batch_size,
                interval_seconds=self.config.bsp_schedule_delay_ms / 1000,
            ),
            config=self.config,
        )
        self.otel_logging_handler = OtelBridgeLoggingHandler(self.logger_provider)
        self.root_logger.addHandler(self.otel_logging_handler)

        self.set_up_console_logging()

    def set_up_console_logging(self):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(self.config.mini_log_format))
        self.root_logger.addHandler(stream_handler)

    def instrument_libraries(self):
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

    def shutdown(self):
        if self.tracer_provider:
            self.tracer_provider.shutdown()

        if self.logger_provider:
            self.logger_provider.shutdown()

        if self.meter_provider:
            self.meter_provider.shutdown()

        if self.otel_logging_handler and self.root_logger:
            self.root_logger.removeHandler(self.otel_logging_handler)
