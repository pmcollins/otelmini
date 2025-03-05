import time
from pathlib import Path
from typing import Mapping, Optional, Sequence

from opentelemetry import trace


class TraceOtelTest:
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
    tracer = trace.get_tracer(__name__)
    print(f"got tracer: {tracer}")
    for i in range(12):
        with tracer.start_as_current_span("foo"):
            time.sleep(0.1)
            print(i)
