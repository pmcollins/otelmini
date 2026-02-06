from otelmini.auto._lib import AutoInstrumentation
from otelmini.env import Config

_instrumentation = None


def _get_instrumentation():
    global _instrumentation
    if _instrumentation is None:
        _instrumentation = AutoInstrumentation(Config())
    return _instrumentation


def set_up_tracing():
    _get_instrumentation().set_up_tracing()


def set_up_logging():
    _get_instrumentation().set_up_logging()


def set_up_metrics():
    _get_instrumentation().set_up_metrics()


def instrument_libraries():
    _get_instrumentation().instrument_libraries()
