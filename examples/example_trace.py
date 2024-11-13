import logging
import time
from typing import Mapping, Optional, Sequence

from opentelemetry import trace
from oteltest import OtelTest, Telemetry

from lib import configure




def run():
    tracer = trace.get_tracer("my-module")

    main_logger = logging.getLogger("main")
    main_logger.info("got tracer %s", tracer)

    i = 0
    main_logger.info("12 spans")
    for _ in range(12):
        with tracer.start_span(f"span-{i}"):
            i += 1
            time.sleep(0.1)
    main_logger.info("12 spans done")

    main_logger.info("start sleeping")
    time.sleep(6)
    main_logger.info("done sleeping")


if __name__ == '__main__':
    configure()
    run()


class MyOtelTest(OtelTest):
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return []

    def wrapper_command(self) -> str:
        return ""

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel: Telemetry, stdout: str, stderr: str, returncode: int) -> None:
        pass

    def is_http(self) -> bool:
        return False
