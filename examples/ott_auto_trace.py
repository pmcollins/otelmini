import time
from typing import Mapping, Optional, Sequence

from opentelemetry import trace

from _lib import package_grpc


class TraceOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return (package_grpc(),)

    def wrapper_command(self) -> str:
        return "otel"

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        print("started")
        return None

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_spans

        assert count_spans(tel)


if __name__ == "__main__":
    tracer = trace.get_tracer(__name__)
    print(f"got tracer: {tracer}")
    for i in range(12):
        with tracer.start_as_current_span("foo"):
            time.sleep(0.1)
            print(i)
