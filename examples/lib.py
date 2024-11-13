import logging

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from otelmini.trace import MiniBSP, OtlpGrpcExporter


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


def configure(daemon=True):
    configure_logging()

    tp = TracerProvider()
    exporter = OtlpGrpcExporter(logging.getLogger("OtlpGrpcExporter"))
    proc = MiniBSP(
        exporter,
        batch_size=12,
        interval_seconds=4,
        logger=logging.getLogger("BatchSpanProcessor"),
        daemon=daemon,
    )
    tp.add_span_processor(proc)
    trace.set_tracer_provider(tp)
    return tp
