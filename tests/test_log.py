import json
import logging
from io import StringIO

from opentelemetry import trace
from opentelemetry.trace import TraceFlags

from otelmini.log import (
    ConsoleLogExporter,
    MiniLogRecord,
    Logger,
    LoggerProvider,
    SeverityNumber,
    _pylog_to_minilog,
)
from otelmini.processor import BatchProcessor
from otelmini.encode import encode_logs_request
from otelmini.trace import MiniTracerProvider
from otelmini.types import Resource


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

    # Emit the log record (convert to MiniLogRecord first)
    mini_log_record = _pylog_to_minilog(log_record, logger_provider.resource)
    logger.emit(mini_log_record)
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


class NoOpProcessor:
    def on_start(self, span):
        pass

    def on_end(self, span):
        pass

    def shutdown(self):
        pass


def test_trace_log_correlation():
    """Logs emitted within a span should capture trace context."""
    # Set up tracer with a no-op processor
    tp = MiniTracerProvider(span_processor=NoOpProcessor())
    tracer = tp.get_tracer(__name__)

    # Create a span and log within it
    with tracer.start_as_current_span("test-span") as span:
        span_context = span.get_span_context()
        log_record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        mini_log = _pylog_to_minilog(log_record)

        # Verify trace context is captured
        assert mini_log.trace_id == span_context.trace_id
        assert mini_log.span_id == span_context.span_id
        assert mini_log.trace_flags == span_context.trace_flags

    tp.shutdown()


def test_log_without_span_has_no_trace_context():
    """Logs emitted outside a span should have no trace context (trace_id=0)."""
    # Ensure we're outside any span by using a fresh context
    from opentelemetry import context
    from opentelemetry.context import Context

    token = context.attach(Context())
    try:
        log_record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        mini_log = _pylog_to_minilog(log_record)

        # trace_id/span_id of 0 means "no associated trace" in OTLP
        assert mini_log.trace_id == 0
        assert mini_log.span_id == 0
    finally:
        context.detach(token)


def test_log_includes_resource():
    """Logs should include resource attributes in export."""
    resource = Resource(attributes={"service.name": "test-service", "env": "test"})
    log_record = MiniLogRecord(
        timestamp=1234567890,
        severity_text="INFO",
        severity_number=SeverityNumber.INFO,
        body="Test message",
        attributes={},
        resource=resource,
    )

    encoded_json = encode_logs_request([log_record])
    decoded = json.loads(encoded_json)

    # Check resource is present
    resource_log = decoded["resourceLogs"][0]
    attrs = {a["key"]: a["value"]["stringValue"] for a in resource_log["resource"]["attributes"]}
    assert attrs["service.name"] == "test-service"
    assert attrs["env"] == "test"


def test_logger_provider_passes_resource_to_logs():
    """LoggerProvider should pass its resource to emitted logs."""
    resource = Resource(attributes={"service.name": "my-service"})

    class CapturingExporter:
        def __init__(self):
            self.logs = []

        def export(self, items):
            self.logs.extend(items)
            return None

    class CapturingProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

        def on_end(self, item):
            self.exporter.logs.append(item)

        def shutdown(self):
            pass

    exporter = CapturingExporter()
    processor = CapturingProcessor(exporter)
    provider = LoggerProvider(log_processor=processor, resource=resource)
    logger = provider.get_logger("test")

    log_record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    mini_log_record = _pylog_to_minilog(log_record, resource)
    logger.emit(mini_log_record)

    assert len(exporter.logs) == 1
    assert exporter.logs[0].get_resource() is resource


def test_logger_provider_force_flush():
    """LoggerProvider.force_flush() should flush all pending logs."""
    from otelmini.export import SingleAttemptResult

    class RecordingExporter:
        def __init__(self):
            self.items = []

        def export(self, items):
            self.items.extend(items)
            return SingleAttemptResult.SUCCESS

    exporter = RecordingExporter()
    processor = BatchProcessor(exporter, batch_size=100, interval_seconds=60)
    provider = LoggerProvider(log_processor=processor)
    logger = provider.get_logger("test")

    log_record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    mini_log = _pylog_to_minilog(log_record, provider.resource)
    logger.emit(mini_log)

    # Not yet exported
    assert len(exporter.items) == 0

    # force_flush exports immediately
    result = provider.force_flush()
    assert result is True
    assert len(exporter.items) == 1

    provider.shutdown()


def test_logger_provider_force_flush_no_processor():
    """LoggerProvider.force_flush() returns True when no processor configured."""
    provider = LoggerProvider()
    assert provider.force_flush() is True
