from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from collections.abc import Sequence
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

from otelmini.env import DEFAULT_OTLP_ENDPOINT

if TYPE_CHECKING:
    from urllib.parse import ParseResult

T = TypeVar("T")


class Exporter(ABC, Generic[T]):
    """Base exporter interface for telemetry data."""

    @abstractmethod
    def export(self, items: Sequence[T]) -> ExportResult:
        """Export telemetry items. Returns SUCCESS or FAILURE."""
        pass

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        """Flush any buffered data. Default implementation is a no-op."""
        return True

    def shutdown(self, timeout_millis: float = 30_000) -> None:
        """Shutdown the exporter. Default implementation is a no-op."""
        pass


class ExportResult(Enum):
    FAILURE = 0
    SUCCESS = 1


class SingleAttemptResult(Enum):
    FAILURE = 0
    SUCCESS = 1
    RETRY = 2


class RetrierResult(Enum):
    FAILURE = 0
    SUCCESS = 1
    MAX_ATTEMPTS_REACHED = 2


class Retrier:
    def __init__(
        self,
        max_retries: int,
        base_seconds: float = 1,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.max_retries = max_retries
        self.base_seconds = base_seconds
        self.sleep = sleep

    def retry(
        self, single_attempt_func: Callable[[], SingleAttemptResult]
    ) -> RetrierResult:
        for attempt in range(self.max_retries + 1):
            resp = single_attempt_func()
            if resp == SingleAttemptResult.SUCCESS:
                return RetrierResult.SUCCESS
            if resp == SingleAttemptResult.FAILURE:
                return RetrierResult.FAILURE
            if resp == SingleAttemptResult.RETRY and attempt < self.max_retries:
                seconds = (2**attempt) * self.base_seconds
                self.sleep(seconds)
        return RetrierResult.MAX_ATTEMPTS_REACHED


# Default retry configuration per OTLP spec
DEFAULT_MAX_RETRIES = 4
DEFAULT_RETRY_BASE_SECONDS = 1.0

# Retryable HTTP status codes per OTLP spec
DEFAULT_RETRYABLE_STATUS_CODES = frozenset(
    [429, 502, 503, 504]
)  # TOO_MANY_REQUESTS, BAD_GATEWAY, SERVICE_UNAVAILABLE, GATEWAY_TIMEOUT

# Default OTLP endpoints (base endpoint defined in env.py)
DEFAULT_TRACE_ENDPOINT = f"{DEFAULT_OTLP_ENDPOINT}/v1/traces"
DEFAULT_LOG_ENDPOINT = f"{DEFAULT_OTLP_ENDPOINT}/v1/logs"
DEFAULT_METRICS_ENDPOINT = f"{DEFAULT_OTLP_ENDPOINT}/v1/metrics"

# Default timeout for HTTP exporters (seconds)
DEFAULT_EXPORTER_TIMEOUT = 30


class _HttpExporter:
    class SingleHttpAttempt:
        def __init__(
            self,
            data: str,
            parsed_url: ParseResult,
            timeout: float,
            retryable_status_codes: frozenset[int],
        ) -> None:
            self.data = data
            self.parsed_url = parsed_url
            self.timeout = timeout
            self.retryable_status_codes = retryable_status_codes

        def export(self) -> SingleAttemptResult:
            from http.client import OK, HTTPConnection

            body = self.data.encode("utf-8")
            conn = HTTPConnection(self.parsed_url.netloc, timeout=self.timeout)
            conn.request(
                "POST", self.parsed_url.path, body, {"Content-Type": "application/json"}
            )
            response = conn.getresponse()
            response.read()
            conn.close()
            if response.status == OK:
                return SingleAttemptResult.SUCCESS
            if response.status in self.retryable_status_codes:
                return SingleAttemptResult.RETRY
            return SingleAttemptResult.FAILURE

    def __init__(
        self,
        endpoint: str,
        timeout: float,
        retrier: Retrier | None = None,
        retryable_status_codes: frozenset[int] | None = None,
    ) -> None:
        from urllib.parse import urlparse

        self.parsed_url = urlparse(endpoint)
        self.timeout = timeout
        self.retrier = retrier or Retrier(DEFAULT_MAX_RETRIES)
        self.retryable_status_codes = (
            retryable_status_codes or DEFAULT_RETRYABLE_STATUS_CODES
        )

    def export(self, data: str) -> ExportResult:
        attempt = _HttpExporter.SingleHttpAttempt(
            data, self.parsed_url, self.timeout, self.retryable_status_codes
        )
        retry_result = self.retrier.retry(attempt.export)
        return (
            ExportResult.SUCCESS
            if retry_result == RetrierResult.SUCCESS
            else ExportResult.FAILURE
        )


class HttpExporterBase(Exporter[T]):
    """Base class for HTTP exporters that handles common init and export pattern."""

    def __init__(
        self,
        endpoint: str,
        timeout: int,
        encoder: Callable[[T], str],
    ) -> None:
        self._exporter = _HttpExporter(endpoint, timeout)
        self._encoder = encoder

    def export(self, items: T) -> ExportResult:
        data = self._encoder(items)
        return self._exporter.export(data)


class ConsoleExporterBase(Exporter[T]):
    """Base class for console exporters that prints encoded telemetry to stdout."""

    def __init__(self, encoder: Callable[[T], str]) -> None:
        self._encoder = encoder

    def export(self, items: T) -> ExportResult:
        print(self._encoder(items))  # noqa: T201
        return ExportResult.SUCCESS
