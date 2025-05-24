from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Generic, Sequence, TypeVar

from grpc import StatusCode

T = TypeVar("T")
_pylogger = logging.getLogger(__package__)


class Exporter(ABC, Generic[T]):
    @abstractmethod
    def export(self, items: Sequence[T]) -> ExportResult:
        pass


class ExportResult(Enum):
    FAILURE = 0
    SUCCESS = 1


class ExponentialBackoff:
    def __init__(self, max_retries, base_seconds=1, sleep=time.sleep, exceptions=(Exception,), abort_retry=lambda _: False):
        self.max_retries = max_retries
        self.base_seconds = base_seconds
        self.sleep = sleep
        self.exceptions = exceptions
        self.abort_retry = abort_retry

    def retry(self, func):
        for attempt in range(self.max_retries + 1):
            _pylogger.debug("Retry attempt %d", attempt)
            try:
                return func()
            except self.exceptions as e:
                if self.abort_retry(e):
                    return None
                if attempt < self.max_retries:
                    seconds = (2 ** attempt) * self.base_seconds
                    _pylogger.warning("Retry will sleep %d seconds", seconds)
                    self.sleep(seconds)
                else:
                    raise ExponentialBackoff.MaxAttemptsError(e) from e
        return None

    class MaxAttemptsError(Exception):
        def __init__(self, last_exception):
            super().__init__("Maximum retries reached")
            self.last_exception = last_exception


def _is_retryable(status_code: StatusCode):
    return status_code in [
        StatusCode.CANCELLED,
        StatusCode.DEADLINE_EXCEEDED,
        StatusCode.RESOURCE_EXHAUSTED,
        StatusCode.ABORTED,
        StatusCode.OUT_OF_RANGE,
        StatusCode.UNAVAILABLE,
        StatusCode.DATA_LOSS,
    ]
