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
from otelmini.encode import encode_logs_request


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

    # Action: Encode the LogRecord to JSON
    encoded_json = encode_logs_request([log_record])
    decoded = json.loads(encoded_json)

    # Assertion: Verify the encoded structure
    assert "resourceLogs" in decoded
    assert len(decoded["resourceLogs"]) == 1

    resource_log = decoded["resourceLogs"][0]
    assert "scopeLogs" in resource_log
    assert len(resource_log["scopeLogs"]) == 1

    scope_log = resource_log["scopeLogs"][0]
    assert "logRecords" in scope_log
    assert len(scope_log["logRecords"]) == 1

    log_rec = scope_log["logRecords"][0]
    assert log_rec["timeUnixNano"] == "1234567890"
    assert log_rec["severityNumber"] == SeverityNumber.INFO.value
    assert log_rec["severityText"] == "INFO"
    assert log_rec["body"]["stringValue"] == "Test log message"
    assert len(log_rec["attributes"]) == 1
    assert log_rec["attributes"][0]["key"] == "test.attribute"
    assert log_rec["attributes"][0]["value"]["stringValue"] == "value"
