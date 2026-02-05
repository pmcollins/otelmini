from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Generic, Sequence, TypeVar

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
    def __init__(self, max_retries, base_seconds=1, sleep=time.sleep):
        self.max_retries = max_retries
        self.base_seconds = base_seconds
        self.sleep = sleep

    def retry(self, single_attempt_func):
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


# Default retryable HTTP status codes per OTLP spec
DEFAULT_RETRYABLE_STATUS_CODES = frozenset([429, 502, 503, 504])  # TOO_MANY_REQUESTS, BAD_GATEWAY, SERVICE_UNAVAILABLE, GATEWAY_TIMEOUT


class _HttpExporter:
    class SingleHttpAttempt:
        def __init__(self, data: str, parsed_url, timeout, retryable_status_codes):
            self.data = data
            self.parsed_url = parsed_url
            self.timeout = timeout
            self.retryable_status_codes = retryable_status_codes

        def export(self):
            from http.client import OK, HTTPConnection
            body = self.data.encode("utf-8")
            conn = HTTPConnection(self.parsed_url.netloc, timeout=self.timeout)
            conn.request("POST", self.parsed_url.path, body, {"Content-Type": "application/json"})
            response = conn.getresponse()
            response.read()
            conn.close()
            if response.status == OK:
                return SingleAttemptResult.SUCCESS
            if response.status in self.retryable_status_codes:
                return SingleAttemptResult.RETRY
            return SingleAttemptResult.FAILURE

    def __init__(self, endpoint, timeout, retrier=None, retryable_status_codes=None):
        from urllib.parse import urlparse
        self.parsed_url = urlparse(endpoint)
        self.timeout = timeout
        self.retrier = retrier or Retrier(4)
        self.retryable_status_codes = retryable_status_codes or DEFAULT_RETRYABLE_STATUS_CODES

    def export(self, data: str):
        attempt = _HttpExporter.SingleHttpAttempt(
            data, self.parsed_url, self.timeout, self.retryable_status_codes
        )
        retry_result = self.retrier.retry(attempt.export)
        return ExportResult.SUCCESS if retry_result == RetrierResult.SUCCESS else ExportResult.FAILURE
