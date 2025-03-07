import logging
import pytest

from otelmini.auto import set_up_logging, manager
from otelmini.log import BatchLogRecordProcessor, ConsoleLogExporter, LoggerProvider, OtelBridgeHandler


@pytest.fixture(autouse=True)
def root_logger():
    """Fixture to save and restore root logger handlers."""
    root_logger = logging.getLogger()
    
    original_handlers = root_logger.handlers[:]
    
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    yield root_logger
    
    manager.shutdown()

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    for handler in original_handlers:
        root_logger.addHandler(handler)


def test_set_up_logging(root_logger):
    # Set up logging with console exporter for testing
    set_up_logging(ConsoleLogExporter())

    # Find our handlers
    otel_handler = None
    stream_handler = None
    for handler in root_logger.handlers:
        if isinstance(handler, OtelBridgeHandler):
            otel_handler = handler
        elif isinstance(handler, logging.StreamHandler):
            stream_handler = handler

    # Verify both handlers exist
    assert otel_handler is not None
    assert stream_handler is not None

    # Verify stream handler is configured correctly
    assert isinstance(stream_handler.formatter, logging.Formatter)
    assert stream_handler.formatter._fmt == logging.BASIC_FORMAT

    # Verify OpenTelemetry handler is configured correctly
    assert isinstance(otel_handler.logger_provider, LoggerProvider)
    assert len(otel_handler.logger_provider.processors) == 1
    assert isinstance(otel_handler.logger_provider.processors[0], BatchLogRecordProcessor)
    assert isinstance(otel_handler.logger_provider.processors[0]._processor.exporter, ConsoleLogExporter)


def test_set_up_logging_with_existing_handlers(root_logger):
    # Set up some existing handlers
    existing_handler = logging.StreamHandler()
    root_logger.addHandler(existing_handler)

    # Set up logging with console exporter for testing
    set_up_logging(ConsoleLogExporter())

    # Verify our handlers exist
    assert existing_handler in root_logger.handlers
    assert any(isinstance(h, OtelBridgeHandler) for h in root_logger.handlers)
    assert any(isinstance(h, logging.StreamHandler) and h != existing_handler for h in root_logger.handlers)

