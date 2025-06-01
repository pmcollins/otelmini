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
            print("Retrying", attempt)
            resp = single_attempt_func()
            print("resp: ", resp)
            if resp == SingleAttemptResult.SUCCESS:
                return RetrierResult.SUCCESS
            elif resp == SingleAttemptResult.FAILURE:
                return RetrierResult.FAILURE
            elif resp == SingleAttemptResult.RETRY:
                if attempt < self.max_retries:
                    seconds = (2 ** attempt) * self.base_seconds
                    print("will sleep {} seconds".format(seconds))
                    self.sleep(seconds)
        return RetrierResult.MAX_ATTEMPTS_REACHED
