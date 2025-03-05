import logging

from otelmini.auto import set_up_logging, set_up_tracing

_pylogger = logging.getLogger(__name__)
_pylogger.warning("otelmini sitecustomize.py running")

set_up_tracing()
# set_up_logging()
