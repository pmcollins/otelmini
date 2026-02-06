"""Requests instrumentation test using opentelemetry-python auto-instrumentation."""

from typing import Mapping, Sequence

from common import BaseRequestsAutoCompareTest


if __name__ == "__main__":
    BaseRequestsAutoCompareTest.run_instrumented_request()


class RequestsAutoOtelpythonOtelTest(BaseRequestsAutoCompareTest):
    def environment_variables(self) -> Mapping[str, str]:
        return {
            "OTEL_SERVICE_NAME": "otel-python-demo",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        }

    def requirements(self) -> Sequence[str]:
        return (
            "opentelemetry-distro",
            "opentelemetry-exporter-otlp",
            "requests",
            "opentelemetry-instrumentation-requests",
        )

    def wrapper_command(self) -> str:
        return "opentelemetry-instrument"
