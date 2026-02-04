import logging
from typing import Mapping, Optional, Sequence

from _lib import package
from otelmini.auto._lib import OTEL_MINI_LOG_FORMAT

MSG = "this is a warning"


class LogsOtelTest:

    def environment_variables(self) -> Mapping[str, str]:
        return {OTEL_MINI_LOG_FORMAT: "%(message)s"}

    def requirements(self) -> Sequence[str]:
        return (package(),)

    def wrapper_command(self) -> str:
        return "otel"

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        print("started")
        return None

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_logs
        assert MSG in stderr, 'MSG in stderr'
        assert count_logs(tel), "count_logs(tel)"


if __name__ == "__main__":
    logging.basicConfig(format="you shouldn't be seeing this: %(asctime)s %(message)s", level=logging.INFO)
    logger = logging.getLogger("ott")
    logger.warning(MSG)
