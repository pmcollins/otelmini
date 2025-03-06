import logging
import time
from pathlib import Path
from typing import Mapping, Optional, Sequence


class LogsOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return ((str(Path(__file__).resolve().parent.parent)),)

    def wrapper_command(self) -> str:
        return "otel"

    def is_http(self) -> bool:
        return False

    def on_start(self) -> Optional[float]:
        print("started")
        return None

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_logs

        assert count_logs(tel)


if __name__ == "__main__":
    logging.basicConfig()
    logger = logging.getLogger()
    for i in range(12):
        logger.warning(f"this is warning {i}")
        time.sleep(0.1)
