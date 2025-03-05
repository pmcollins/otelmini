from __future__ import annotations

import logging
import time

_pylogger = logging.getLogger(__name__)


class ExponentialBackoff:
    def __init__(self, max_retries, base_seconds=1, sleep=time.sleep, exceptions=(Exception,)):
        self.max_retries = max_retries
        self.base_seconds = base_seconds
        self.sleep = sleep
        self.exceptions = exceptions

    def retry(self, func):
        for attempt in range(self.max_retries + 1):
            _pylogger.debug("Retry attempt %d", attempt)
            try:
                return func()
            except self.exceptions as e:
                if attempt < self.max_retries:
                    seconds = (2**attempt) * self.base_seconds
                    _pylogger.warning("Retry will sleep %d seconds", seconds)
                    self.sleep(seconds)
                else:
                    raise ExponentialBackoff.MaxAttemptsError(e) from e
        return None

    class MaxAttemptsError(Exception):
        def __init__(self, last_exception):
            super().__init__("Maximum retries reached")
            self.last_exception = last_exception
