from otelmini.auto._lib import AutoInstrumentationManager
from otelmini.env import Config

manager = AutoInstrumentationManager(Config())


def set_up_tracing():
    manager.set_up_tracing()


def set_up_logging():
    manager.set_up_logging()


def set_up_metrics():
    manager.set_up_metrics()


def instrument_libraries():
    manager.instrument_libraries()
