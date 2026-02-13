"""Requests instrumentation test using otelmini auto-instrumentation."""

from pathlib import Path
from typing import Mapping, Sequence

from common import BaseRequestsAutoCompareTest


if __name__ == "__main__":
    BaseRequestsAutoCompareTest.run_instrumented_request()


class RequestsAutoOtelminiOtelTest(BaseRequestsAutoCompareTest):
    def environment_variables(self) -> Mapping[str, str]:
        return {
            "OTEL_SERVICE_NAME": "otelmini-demo",
        }

    def requirements(self) -> Sequence[str]:
        parent = str(Path(__file__).resolve().parent.parent.parent)
        return (
            parent,
            "requests",
            "opentelemetry-instrumentation-requests",
        )

    def wrapper_command(self) -> str:
        return "otel"
