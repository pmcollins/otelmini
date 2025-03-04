import logging
import subprocess
import sys

from opentelemetry import trace

from otelmini.log import BatchLogRecordProcessor, ConsoleLogExporter, LoggerProvider, OtelBridgeHandler
from otelmini.trace import BatchProcessor, GrpcSpanExporter, TracerProvider


logging.basicConfig()
_pylogger = logging.getLogger(__name__)

def auto_instrument():
    _pylogger.warning("OtelMiniAutoInstrumentor configure running")
    _pylogger.warning(sys.argv)
    set_up_tracing()
    set_up_logging()
    cmd = sys.argv[1:]
    subprocess.run(cmd)


def set_up_tracing():
    tracer_provider = TracerProvider(BatchProcessor(
        GrpcSpanExporter(),
        batch_size=144,
        interval_seconds=12,
    ))
    trace.set_tracer_provider(tracer_provider)


def set_up_logging():
    logger_provider = LoggerProvider([(BatchLogRecordProcessor(ConsoleLogExporter()))])
    logging.getLogger().addHandler(OtelBridgeHandler(logger_provider))
