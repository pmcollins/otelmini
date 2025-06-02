from otelmini.auto._lib import AutoInstrumentationManager, Env

manager = AutoInstrumentationManager(Env())


def set_up_tracing():
    manager.set_up_tracing()


def set_up_logging():
    manager.set_up_logging()
