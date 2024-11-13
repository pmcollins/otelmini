import logging
import time

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from examples.lib import configure_logging
from otelmini.trace import MiniBSP, OtlpGrpcExporter

if __name__ == '__main__':
    configure_logging()
    tp = TracerProvider()
    exporter = OtlpGrpcExporter(logging.getLogger("OtlpGrpcExporter"))
    proc = MiniBSP(
        exporter,
        batch_size=12,
        interval_seconds=4,
        logger=logging.getLogger("BatchSpanProcessor"),
        daemon=True,
    )
    tp.add_span_processor(proc)
    trace.set_tracer_provider(tp)

    tracer = tp.get_tracer("fun")
    while True:
        with tracer.start_as_current_span("x"):
            time.sleep(6)
            print(".")
