import logging
import time
from os.path import abspath, dirname
from pathlib import Path
from typing import Mapping, Optional, Sequence

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from oteltest import OtelTest, Telemetry
from oteltest.telemetry import count_spans

from otelmini.trace import BatchProcessor, GrpcExporter


def configure_py_logging():
    class AlignedFormatter(logging.Formatter):
        def format(self, record):
            record.levelname = record.levelname.ljust(8)
            record.name = record.name.ljust(24)
            return super().format(record)

    logging.basicConfig(level=logging.DEBUG)
    formatter = AlignedFormatter("%(levelname)s %(name)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)


def configure_otel():
    tp = TracerProvider()
    exporter = GrpcExporter(logging.getLogger("OtlpGrpcExporter"))
    proc = BatchProcessor(
        exporter,
        batch_size=24,
        interval_seconds=6,
        logger=logging.getLogger("BatchSpanProcessor"),
        daemon=True,
    )
    tp.add_span_processor(proc)
    trace.set_tracer_provider(tp)


def send_spans():
    logger = logging.getLogger("main")
    tracer = trace.get_tracer("my-module")
    logger.info("sending span")
    with tracer.start_span(f"span"):
        time.sleep(0.1)
    logger.info("done")


if __name__ == '__main__':
    configure_py_logging()
    configure_otel()
    send_spans()


class MyOtelTest(OtelTest):
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        parent = str(Path(__file__).resolve().parent.parent)
        return (parent,)

    def wrapper_command(self) -> str:
        return ""

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel: Telemetry, stdout: str, stderr: str, returncode: int) -> None:
        assert count_spans(tel) == 1

    def is_http(self) -> bool:
        return False
