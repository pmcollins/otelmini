from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional, Sequence

from opentelemetry._logs import LogRecord as ApiLogRecord
from opentelemetry._logs import Logger as ApiLogger
from opentelemetry._logs import LoggerProvider as ApiLoggerProvider
from opentelemetry._logs import SeverityNumber
from opentelemetry.trace import TraceFlags

if TYPE_CHECKING:
    from otelmini.processor import Processor
from opentelemetry.util.types import Attributes

from otelmini._lib import Exporter, ExportResult, _HttpExporter
from otelmini.encode import encode_logs_request


class MiniLogRecord(ApiLogRecord):
    def __init__(
        self,
        timestamp: Optional[int] = None,
        observed_timestamp: Optional[int] = None,
        trace_id: Optional[int] = None,
        span_id: Optional[int] = None,
        trace_flags: Optional[TraceFlags] = None,
        severity_text: Optional[str] = None,
        severity_number: Optional[SeverityNumber] = None,
        body: Optional[Any] = None,
        attributes: Optional[Attributes] = None,
    ):
        super().__init__(
            timestamp=timestamp,
            observed_timestamp=observed_timestamp,
            trace_id=trace_id,
            span_id=span_id,
            trace_flags=trace_flags,
            severity_text=severity_text,
            severity_number=severity_number,
            body=body,
            attributes=attributes or {},
        )

    def __str__(self) -> str:
        return f"MiniLogRecord(severity={self.severity_text}, body='{self.body}')"


class LogExportError(Exception):
    def __init__(self, message: str = "Error exporting logs"):
        super().__init__(message)


class ConsoleLogExporter(Exporter[MiniLogRecord]):
    def export(self, items: Sequence[MiniLogRecord]) -> ExportResult:
        print(encode_logs_request(items))  # noqa: T201
        return ExportResult.SUCCESS


class HttpLogExporter(Exporter[MiniLogRecord]):
    def __init__(self, endpoint="http://localhost:4318/v1/logs", timeout=30):
        self._exporter = _HttpExporter(endpoint, timeout)

    def export(self, logs: Sequence[MiniLogRecord]) -> ExportResult:
        data = encode_logs_request(logs)
        return self._exporter.export(data)


class Logger(ApiLogger):
    def __init__(
        self,
        name: str,
        logger_provider: LoggerProvider,
        version: Optional[str] = None,
        schema_url: Optional[str] = None,
        attributes: Optional[Attributes] = None,
    ):
        self._name = name
        self._version = version
        self._schema_url = schema_url
        self._attributes = attributes
        self._logger_provider = logger_provider

    def emit(self, pylog_record: logging.LogRecord) -> None:
        mini_log_record = _pylog_to_minilog(pylog_record)
        self._logger_provider.log_processor.on_end(mini_log_record)


def _pylog_to_minilog(pylog_record: logging.LogRecord) -> MiniLogRecord:
    return MiniLogRecord(
        timestamp=int(pylog_record.created * 1e9),  # Convert to nanoseconds
        observed_timestamp=int(pylog_record.created * 1e9),
        trace_id=None,  # LogRecord does not have trace_id
        span_id=None,  # LogRecord does not have span_id
        trace_flags=None,  # LogRecord does not have trace_flags
        severity_text=pylog_record.levelname,
        severity_number=_get_severity_number(pylog_record.levelno),
        body=pylog_record.getMessage(),
        attributes={
            "filename": pylog_record.filename,
            "funcName": pylog_record.funcName,
            "lineno": pylog_record.lineno,
            "module": pylog_record.module,
            "name": pylog_record.name,
            "pathname": pylog_record.pathname,
            "process": pylog_record.process,
            "processName": pylog_record.processName,
            "thread": pylog_record.thread,
            "threadName": pylog_record.threadName,
        },
    )


class LoggerProvider(ApiLoggerProvider):
    def __init__(self, log_processor: Optional[Processor[MiniLogRecord]] = None) -> None:
        self.log_processor = log_processor

    def get_logger(
        self,
        name: str,
        version: Optional[str] = None,
        schema_url: Optional[str] = None,
        attributes: Optional[Attributes] = None,
    ) -> Logger:
        return Logger(
            name=name,
            logger_provider=self,
            version=version,
            schema_url=schema_url,
            attributes=attributes,
        )

    def shutdown(self) -> None:
        if self.log_processor:
            self.log_processor.shutdown()


# Mapping from Python logging levels to OpenTelemetry severity numbers
# Ordered from highest to lowest for threshold-based lookup
_SEVERITY_MAP = (
    (logging.CRITICAL, SeverityNumber.FATAL),
    (logging.ERROR, SeverityNumber.ERROR),
    (logging.WARNING, SeverityNumber.WARN),
    (logging.INFO, SeverityNumber.INFO),
    (logging.DEBUG, SeverityNumber.DEBUG),
)


def _get_severity_number(levelno: int) -> SeverityNumber:
    """Map Python logging level to OpenTelemetry severity number."""
    for threshold, severity in _SEVERITY_MAP:
        if levelno >= threshold:
            return severity
    return SeverityNumber.TRACE


class OtelBridgeLoggingHandler(logging.Handler):
    def __init__(self, logger_provider: LoggerProvider, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        self.logger_provider = logger_provider

    def emit(self, record: logging.LogRecord) -> None:
        try:
            logger = self.logger_provider.get_logger(record.name)
            logger.emit(record)
        except (AttributeError, TypeError):
            logging.exception("error emitting log record")
            self.handleError(record)
