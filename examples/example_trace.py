import logging
import time
from typing import Mapping, Optional, Sequence

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from oteltest import OtelTest, Telemetry

from otelmini.trace import BatchSpanProcessor, OtlpGrpcExporter


def configure_logging():
    class AlignedFormatter(logging.Formatter):
        def format(self, record):
            record.levelname = record.levelname.ljust(8)
            record.name = record.name.ljust(24)
            return super().format(record)

    logging.basicConfig(level=logging.DEBUG)
    formatter = AlignedFormatter("%(levelname)s %(name)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)


def configure():
    configure_logging()

    tp = TracerProvider()
    exporter = OtlpGrpcExporter(logging.getLogger("OtlpGrpcExporter"))
    proc = BatchSpanProcessor(
        exporter,
        batch_size=12,
        interval_seconds=4,
        logger=logging.getLogger("BatchSpanProcessor")
    )
    tp.add_span_processor(proc)
    trace.set_tracer_provider(tp)
    return tp


def run():
    tracer = trace.get_tracer("my-module")

    main_logger = logging.getLogger("main")
    main_logger.info("got tracer %s", tracer)

    i = 0
    main_logger.info("12 spans")
    for _ in range(12):
        with tracer.start_span(f"span-{i}"):
            i += 1
            time.sleep(0.1)
    main_logger.info("12 spans done")

    main_logger.info("start sleeping")
    time.sleep(6)
    main_logger.info("done sleeping")


if __name__ == '__main__':
    configure()
    run()


class MyOtelTest(OtelTest):
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        return []

    def wrapper_command(self) -> str:
        return ""

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel: Telemetry, stdout: str, stderr: str, returncode: int) -> None:
        pass

    def is_http(self) -> bool:
        return False
