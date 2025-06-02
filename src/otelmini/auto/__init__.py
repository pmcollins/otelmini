from otelmini.auto._lib import AutoInstrumentationManager, Env

# Global instance to track OpenTelemetry components
manager = AutoInstrumentationManager(Env())


# Convenience functions that delegate to the global manager
def set_up_tracing():
    manager.set_up_tracing()


def set_up_logging():
    manager.set_up_logging()
