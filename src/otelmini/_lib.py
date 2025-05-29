from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Generic, Sequence, TypeVar

T = TypeVar("T")
_pylogger = logging.getLogger(__package__)


class Exporter(ABC, Generic[T]):
    @abstractmethod
    def export(self, items: Sequence[T]) -> ExportResult:
        pass


class ExportResult(Enum):
    FAILURE = 0
    SUCCESS = 1


class Retrier:
    def __init__(self, max_retries, base_seconds=1, sleep=time.sleep, exceptions=(Exception,), should_retry=lambda _: True):
        self.max_retries = max_retries
        self.base_seconds = base_seconds
        self.sleep = sleep
        self.exceptions = exceptions
        self.should_retry = should_retry

    def retry(self, func):
        for attempt in range(self.max_retries + 1):
            _pylogger.debug("Retry attempt %d", attempt)
            try:
                return func()
            except self.exceptions as e:
                if not self.should_retry(e):
                    return None
                if attempt < self.max_retries:
                    seconds = (2 ** attempt) * self.base_seconds
                    _pylogger.warning("Retry will sleep %d seconds", seconds)
                    self.sleep(seconds)
                else:
                    raise Retrier.MaxAttemptsError(e) from e
        return None

    class MaxAttemptsError(Exception):
        def __init__(self, last_exception):
            super().__init__("Maximum retries reached")
            self.last_exception = last_exception
