"""
Test that BatchProcessor exports logs when batch_size is reached.
Creates 36 log records with batch_size=24, so we expect:
- 1 export triggered by batch size (24 logs)
- 1 export on shutdown (12 logs)
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
        from oteltest.telemetry import count_logs, MessageToDict

        # Should have received all 36 logs
        assert count_logs(tel) == 36, f"expected 36 logs, got {count_logs(tel)}"

        # Should have 2 log requests (exports)
        assert len(tel.log_requests) == 2, f"expected 2 exports, got {len(tel.log_requests)}"

        # First export should have 24 logs (batch size trigger)
        req1 = MessageToDict(tel.log_requests[0].pbreq)
        logs1 = req1["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        assert len(logs1) == 24, f"first export: expected 24 logs, got {len(logs1)}"

        # Second export should have 12 logs (shutdown flush)
        req2 = MessageToDict(tel.log_requests[1].pbreq)
        logs2 = req2["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        assert len(logs2) == 12, f"second export: expected 12 logs, got {len(logs2)}"


if __name__ == "__main__":
    provider = LoggerProvider(
        BatchProcessor(
            HttpLogExporter(),
            batch_size=24,
            interval_seconds=600,  # 10 min - won't fire during test
        )
    )
    handler = OtelBridgeLoggingHandler(provider)

    logger = logging.getLogger("test")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    # Create 36 logs quickly - should trigger batch export at 24
    for i in range(36):
        logger.info(f"log message {i}")
        time.sleep(0.05)

    provider.shutdown()
