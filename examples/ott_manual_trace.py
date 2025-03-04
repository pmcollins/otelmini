import time
from pathlib import Path
from typing import Mapping, Optional, Sequence

from opentelemetry import trace

from otelmini.distro import set_up_tracing

set_up_tracing()

tracer = trace.get_tracer(__name__)
for _ in range(144):
    with tracer.start_span("foo"):
        time.sleep(1)
        print(".")


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
