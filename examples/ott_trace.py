import logging
import time

from opentelemetry import trace

tracer = trace.get_tracer("imn")
with tracer.start_as_current_span(""):
    time.sleep(1)
    print("x")
    logging.getLogger().warning("w")
