from otelmini.auto._lib import AutoInstrumentation
from otelmini.env import Config

instrumentation = AutoInstrumentation(Config())


def set_up_tracing():
    instrumentation.set_up_tracing()


def set_up_logging():
    instrumentation.set_up_logging()


def set_up_metrics():
    instrumentation.set_up_metrics()


def instrument_libraries():
    instrumentation.instrument_libraries()
