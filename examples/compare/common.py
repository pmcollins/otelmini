"""Shared constants and configuration for otelmini vs otel-python comparison tests."""

from pathlib import Path
from typing import Mapping, Optional, Sequence

# Span configuration - identical for both implementations
SPAN_NAME = "test-operation"
SPAN_ATTRIBUTES = {"test.key": "test-value", "test.count": 42}
EVENT_NAME = "test-event"
EVENT_ATTRIBUTES = {"event.key": "event-value"}


class BaseCompareTest:
    """Base oteltest class with common configuration."""

    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_spans

        assert count_spans(tel) == 1, f"Expected 1 span, got {count_spans(tel)}"
        print(f"stdout:\n{stdout}")
        print(f"stderr:\n{stderr}")
        print(f"returncode: {returncode}")
