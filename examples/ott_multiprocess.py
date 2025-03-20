import time
from pathlib import Path
from typing import Mapping, Optional, Sequence

from otelmini.processor import RemoteBatchProcessor
from otelmini.trace import GrpcSpanExporter, MiniTracer


class MultiprocOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return ((str(Path(__file__).resolve().parent.parent)),)

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return False

    def on_start(self) -> Optional[float]:
        print("started")
        return None

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        print("stopped")


if __name__ == "__main__":
    exporter = GrpcSpanExporter()
    processor = RemoteBatchProcessor(exporter, batch_size=144, interval_seconds=12)
    tracer = MiniTracer(processor)
    for i in range(12):
        with tracer.start_as_current_span("foo"):
            time.sleep(1)
            print(i)
