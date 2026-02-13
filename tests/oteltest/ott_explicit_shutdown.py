import os
import time
from pathlib import Path
from typing import Mapping, Optional, Sequence

from opentelemetry import trace

from otelmini.processor import BatchProcessor
from otelmini.trace import HttpSpanExporter, MiniTracerProvider


class OtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        parent = str(Path(__file__).resolve().parent.parent)
        return (parent,)

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_spans

        assert count_spans(tel) == 13


if __name__ == '__main__':
    os.environ["OTEL_SERVICE_NAME"] = "manual"
    tp = MiniTracerProvider(
        BatchProcessor(
            HttpSpanExporter(),
            batch_size=24,
            interval_seconds=6,
        )
    )
    trace.set_tracer_provider(tp)
    tracer = tp.get_tracer(__name__)
    with tracer.start_as_current_span("ott-manual-spans"):
        for i in range(12):
            with tracer.start_as_current_span(f"span-{i}"):
                print(f"main: i={i}")
                time.sleep(0.2)
    tp.shutdown()
