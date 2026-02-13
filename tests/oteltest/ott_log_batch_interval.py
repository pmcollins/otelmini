"""
Test that BatchProcessor exports logs when interval_seconds elapses.
Creates 12 log records over ~6 seconds with interval_seconds=2, so we expect
multiple interval-triggered exports before shutdown.
"""

import logging
import time
from typing import Mapping, Optional, Sequence

from _lib import package
from otelmini.log import HttpLogExporter, LoggerProvider, OtelBridgeLoggingHandler
from otelmini.processor import BatchProcessor


class OtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return (package(),)

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        return None

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_logs

        # Should have received all 12 logs
        assert count_logs(tel) == 12, f"expected 12 logs, got {count_logs(tel)}"

        # Should have multiple exports (interval triggered + shutdown)
        # With 12 logs at 0.5s each = 6s total, and 2s interval,
        # we expect around 3-4 exports (timing dependent)
        num_exports = len(tel.log_requests)
        assert num_exports >= 2, f"expected at least 2 exports, got {num_exports}"


if __name__ == "__main__":
    provider = LoggerProvider(
        BatchProcessor(
            HttpLogExporter(),
            batch_size=1000,  # Won't hit batch size
            interval_seconds=2,
        )
    )
    handler = OtelBridgeLoggingHandler(provider)

    logger = logging.getLogger("test")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    # Create 12 logs slowly - should trigger interval exports
    for i in range(12):
        logger.info(f"log message {i}")
        time.sleep(0.5)

    provider.shutdown()
