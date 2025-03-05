import json
import logging
from io import StringIO

from otelmini.log import (
    ConsoleLogExporter,
    LogRecord,
    Logger,
    LoggerProvider,
    BatchLogRecordProcessor,
    SeverityNumber,
)


def test_basic_logging():
    # Setup
    console_exporter = ConsoleLogExporter()
    batch_processor = BatchLogRecordProcessor(console_exporter)
    logger_provider = LoggerProvider([batch_processor])
    logger = logger_provider.get_logger("test_logger")

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.propagate = True
    
    # Capture output
    string_stream = StringIO()
    handler = logging.StreamHandler(string_stream)
    handler.setFormatter(logging.Formatter('%(message)s'))
    handler.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    # Create a test log record
    log_record = LogRecord(
        timestamp=1234567890,
        severity_text="INFO",
        severity_number=SeverityNumber.INFO,
        body="Test log message",
        attributes={"test.attribute": "value"}
    )

    # Emit the log record
    logger.emit(log_record)
    logger_provider.force_flush()

    # Get the logged output
    logged_output = string_stream.getvalue().strip()
    log_data = json.loads(logged_output)

    # Verify the log contents
    assert log_data["timestamp"] == 1234567890
    assert log_data["severity_text"] == "INFO"
    assert log_data["body"] == "Test log message"
    assert log_data["attributes"]["test.attribute"] == "value"

    # Cleanup
    root_logger.removeHandler(handler)
    logger_provider.shutdown() 