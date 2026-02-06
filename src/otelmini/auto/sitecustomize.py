from otelmini.auto import instrument_libraries, set_up_logging, set_up_metrics, set_up_tracing

set_up_tracing()
set_up_logging()
set_up_metrics()
instrument_libraries()
