from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Generic, Sequence, TypeVar

T = TypeVar("T")


class Exporter(ABC, Generic[T]):
    @abstractmethod
    def export(self, items: Sequence[T]) -> ExportResult:
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


class _HttpExporter:
    class SingleHttpAttempt:
        def __init__(self, request, parsed_url, timeout):
            self.request = request
            self.parsed_url = parsed_url
            self.timeout = timeout

        def export(self):
            from http.client import HTTPConnection, OK, TOO_MANY_REQUESTS, BAD_GATEWAY, SERVICE_UNAVAILABLE, GATEWAY_TIMEOUT
            data = self.request.SerializeToString()
            conn = HTTPConnection(self.parsed_url.netloc, timeout=self.timeout)
            conn.request("POST", self.parsed_url.path, data, {"Content-Type": "application/x-protobuf"})
            response = conn.getresponse()
            response.read()
            conn.close()
            if response.status == OK:
                return SingleAttemptResult.SUCCESS
            if response.status in [TOO_MANY_REQUESTS, BAD_GATEWAY, SERVICE_UNAVAILABLE, GATEWAY_TIMEOUT]:
                return SingleAttemptResult.RETRY
            return SingleAttemptResult.FAILURE

    def __init__(self, endpoint, timeout):
        from urllib.parse import urlparse
        self.parsed_url = urlparse(endpoint)
        self.timeout = timeout
        self.retrier = Retrier(4)

    def export(self, request):
        attempt = _HttpExporter.SingleHttpAttempt(request, self.parsed_url, self.timeout)
        retry_result = self.retrier.retry(attempt.export)
        return ExportResult.SUCCESS if retry_result == RetrierResult.SUCCESS else ExportResult.FAILURE
