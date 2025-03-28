import logging
import time
from pathlib import Path
from typing import Mapping, Optional, Sequence

from otelmini.auto import set_up_logging
from otelmini.auto._lib import OTEL_MINI_LOG_FORMAT


class LogsOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {OTEL_MINI_LOG_FORMAT: "%(message)s"}

    def requirements(self) -> Sequence[str]:
        return ((str(Path(__file__).resolve().parent.parent)),)

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return False

    def on_start(self) -> Optional[float]:
        print("started")
        return None

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_logs

        assert count_logs(tel)


if __name__ == "__main__":
    set_up_logging()
    logger = logging.getLogger()
    for i in range(144):
        logger.warning(f"this is warning {i}")
        print(i)
        time.sleep(0.1)
