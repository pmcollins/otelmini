"""Centralized environment variable configuration.

Config is a simple data class that loads OTEL environment variables.
Pass it explicitly to components that need it.

Usage:
    from otelmini.env import Config

    # Load from os.environ
    config = Config()

    # Load from custom dict (for testing)
    config = Config(Env({"OTEL_SERVICE_NAME": "test-service"}))

    # Pass to components
    resource = create_default_resource(config)
    tp = MiniTracerProvider(processor, config=config)

    # Inspect
    print(config.as_dict())
"""

import logging
import os
from typing import Optional

# Environment variable names
OTEL_SERVICE_NAME = "OTEL_SERVICE_NAME"
OTEL_RESOURCE_ATTRIBUTES = "OTEL_RESOURCE_ATTRIBUTES"
OTEL_BSP_MAX_EXPORT_BATCH_SIZE = "OTEL_BSP_MAX_EXPORT_BATCH_SIZE"
OTEL_BSP_SCHEDULE_DELAY = "OTEL_BSP_SCHEDULE_DELAY"
OTEL_EXPORTER_OTLP_ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT = "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT = "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"
OTEL_EXPORTER_OTLP_LOGS_ENDPOINT = "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"
OTEL_TRACES_EXPORTER = "OTEL_TRACES_EXPORTER"
OTEL_METRICS_EXPORTER = "OTEL_METRICS_EXPORTER"
OTEL_LOGS_EXPORTER = "OTEL_LOGS_EXPORTER"
OTEL_METRIC_EXPORT_INTERVAL = "OTEL_METRIC_EXPORT_INTERVAL"
OTEL_MINI_LOG_FORMAT = "OTEL_MINI_LOG_FORMAT"

# Default OTLP endpoint (single source of truth)
DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"


class Env:
    """Wrapper around environment variables with typed accessors."""

    def __init__(self, store: Optional[dict] = None):
        self._store = store if store is not None else os.environ

    def get(self, key: str, default: str = "") -> str:
        return self._store.get(key, default)

    def get_int(self, key: str, default: int) -> int:
        val = self._store.get(key, "")
        if not val:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self._store.get(key, "")
        if not val:
            return default
        return val.strip().lower() == "true"


class Config:
    """Configuration loaded from OTEL environment variables.

    All values are loaded at construction time and stored as attributes.
    """

    def __init__(self, env: Optional[Env] = None):
        """Load configuration from environment.

        Args:
            env: Optional Env instance (for testing). Defaults to os.environ.
        """
        if env is None:
            env = Env()

        # Resource
        self.service_name = env.get(OTEL_SERVICE_NAME, "unknown_service")
        self.resource_attributes = env.get(OTEL_RESOURCE_ATTRIBUTES, "")

        # Batch Span Processor
        self.bsp_batch_size = env.get_int(OTEL_BSP_MAX_EXPORT_BATCH_SIZE, 512)
        self.bsp_schedule_delay_ms = env.get_int(OTEL_BSP_SCHEDULE_DELAY, 5000)

        # Exporter endpoints
        self.exporter_endpoint = env.get(
            OTEL_EXPORTER_OTLP_ENDPOINT, DEFAULT_OTLP_ENDPOINT
        )
        self.exporter_traces_endpoint = env.get(OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, "")
        self.exporter_metrics_endpoint = env.get(
            OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, ""
        )
        self.exporter_logs_endpoint = env.get(OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, "")

        # Exporter selection
        self.traces_exporter = env.get(OTEL_TRACES_EXPORTER, "otlp")
        self.metrics_exporter = env.get(OTEL_METRICS_EXPORTER, "otlp")
        self.logs_exporter = env.get(OTEL_LOGS_EXPORTER, "otlp")

        # Metric reader
        self.metric_export_interval_ms = env.get_int(OTEL_METRIC_EXPORT_INTERVAL, 10000)

        # otelmini-specific
        self.mini_log_format = env.get(OTEL_MINI_LOG_FORMAT, logging.BASIC_FORMAT)

    def as_dict(self) -> dict:
        """Return all configuration values as a dictionary."""
        return {
            "service_name": self.service_name,
            "resource_attributes": self.resource_attributes,
            "bsp_batch_size": self.bsp_batch_size,
            "bsp_schedule_delay_ms": self.bsp_schedule_delay_ms,
            "exporter_endpoint": self.exporter_endpoint,
            "exporter_traces_endpoint": self.exporter_traces_endpoint,
            "exporter_metrics_endpoint": self.exporter_metrics_endpoint,
            "exporter_logs_endpoint": self.exporter_logs_endpoint,
            "traces_exporter": self.traces_exporter,
            "metrics_exporter": self.metrics_exporter,
            "logs_exporter": self.logs_exporter,
            "metric_export_interval_ms": self.metric_export_interval_ms,
            "mini_log_format": self.mini_log_format,
        }

    def __repr__(self) -> str:
        return f"Config({self.as_dict()})"
