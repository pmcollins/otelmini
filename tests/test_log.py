import json
import logging
from io import StringIO

from otelmini.log import (
    ConsoleLogExporter,
    MiniLogRecord,
    Logger,
    LoggerProvider,
    SeverityNumber,
)
from otelmini.processor import BatchProcessor
from opentelemetry.proto.logs.v1.logs_pb2 import LogRecord as PB2LogRecord
from otelmini.log import encode_log_record


def test_basic_logging(capsys):
    # Setup
    console_exporter = ConsoleLogExporter()
    batch_processor = BatchProcessor(console_exporter, batch_size=512, interval_seconds=5)
    logger_provider = LoggerProvider(batch_processor)
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

    # Create a test log record directly as a LogRecord
    log_record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test log message",
        args=(),
        exc_info=None,
    )

    # Emit the log record
    logger.emit(log_record)
    batch_processor.force_flush()

    # Capture the output
    captured = capsys.readouterr()
    logged_output = captured.out.strip()

    assert len(logged_output) > 0

    # Cleanup
    root_logger.removeHandler(handler)
    batch_processor.shutdown()


def test_encode_log_record():
    # Setup: Create a LogRecord with known values
    log_record = MiniLogRecord(
        timestamp=1234567890,
        severity_text="INFO",
        severity_number=SeverityNumber.INFO,
        body="Test log message",
        attributes={"test.attribute": "value"}
    )

    # Action: Encode the LogRecord
    encoded_record = encode_log_record(log_record)

    # Assertion: Verify the encoded PB2LogRecord
    assert isinstance(encoded_record, PB2LogRecord)
    assert encoded_record.time_unix_nano == 1234567890
    assert encoded_record.severity_number == SeverityNumber.INFO.value
    assert encoded_record.severity_text == "INFO"
    assert encoded_record.body.string_value == "Test log message"
    assert len(encoded_record.attributes) == 1
    assert encoded_record.attributes[0].key == "test.attribute"
    assert encoded_record.attributes[0].value.string_value == "value"
