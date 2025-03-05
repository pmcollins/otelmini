import logging
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
        print("stopped")


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.warning("this is a warning")
