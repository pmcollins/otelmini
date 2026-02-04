from __future__ import annotations

import logging
from abc import abstractmethod
from enum import Enum
from typing import Any, Optional, Sequence

from opentelemetry._logs import LogRecord as ApiLogRecord
from opentelemetry._logs import Logger as ApiLogger
from opentelemetry._logs import LoggerProvider as ApiLoggerProvider
from opentelemetry._logs import SeverityNumber
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest as PB2ExportLogsServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue as PB2AnyValue
from opentelemetry.proto.common.v1.common_pb2 import KeyValue as PB2KeyValue
from opentelemetry.proto.logs.v1.logs_pb2 import LogRecord as PB2LogRecord
from opentelemetry.proto.logs.v1.logs_pb2 import ResourceLogs as PB2ResourceLogs
from opentelemetry.proto.logs.v1.logs_pb2 import ScopeLogs as PB2ScopeLogs
from opentelemetry.trace import TraceFlags
from opentelemetry.util.types import Attributes

from otelmini._lib import Exporter, ExportResult, _HttpExporter


class LogExportResult(Enum):
    SUCCESS = 0
    FAILURE = 1


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


class LogExportError(Exception):
    def __init__(self, message: str = "Error exporting logs"):
        super().__init__(message)


class LogRecordExporter(Exporter[MiniLogRecord]):
    @abstractmethod
    def export(self, logs: Sequence[MiniLogRecord]) -> ExportResult:
        pass

    @abstractmethod
    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        pass

    @abstractmethod
    def shutdown(self, timeout_millis: Optional[int] = None) -> None:
        pass


class ConsoleLogExporter(LogRecordExporter):
    def export(self, logs: Sequence[MiniLogRecord]) -> ExportResult:
        try:
            for log in logs:
                print(f"log: {log}")  # noqa: T201
        except Exception as e:
            raise LogExportError from e
        else:
            return ExportResult.SUCCESS

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        pass

    def shutdown(self, timeout_millis: Optional[int] = None) -> None:
        pass


class HttpLogExporter(LogRecordExporter):
    def __init__(self, endpoint="http://localhost:4318/v1/logs", timeout=30):
        self._exporter = _HttpExporter(endpoint, timeout)

    def export(self, logs: Sequence[MiniLogRecord]) -> ExportResult:
        request = mk_log_request(logs)
        return self._exporter.export(request)

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        pass

    def shutdown(self, timeout_millis: Optional[int] = None) -> None:
        pass


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


def _pylog_to_minilog(pylog_record):
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
    def __init__(self, log_processor=None):
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


def _get_severity_number(levelno):
    if levelno >= logging.CRITICAL:
        return SeverityNumber.FATAL
    if levelno >= logging.ERROR:
        return SeverityNumber.ERROR
    if levelno >= logging.WARNING:
        return SeverityNumber.WARN
    if levelno >= logging.INFO:
        return SeverityNumber.INFO
    if levelno >= logging.DEBUG:
        return SeverityNumber.DEBUG
    return SeverityNumber.TRACE


class OtelBridgeLoggingHandler(logging.Handler):
    def __init__(self, logger_provider, level=logging.NOTSET):
        super().__init__(level=level)
        self.logger_provider = logger_provider

    def emit(self, record: logging.LogRecord):
        try:
            logger = self.logger_provider.get_logger(record.name)
            logger.emit(record)
        except (AttributeError, TypeError):
            logging.exception("error emitting log record")
            self.handleError(record)


def mk_log_request(logs: Sequence[MiniLogRecord]) -> PB2ExportLogsServiceRequest:
    req = PB2ExportLogsServiceRequest()
    for log in logs:
        # Simplified logging: just append the log message as a string
        log_record = PB2LogRecord(
            time_unix_nano=log.timestamp or 0,
            severity_number=log.severity_number.value if log.severity_number else 0,
            severity_text=log.severity_text or "",
            body=PB2AnyValue(string_value=str(log.body) if log.body else ""),
            attributes=[
                PB2KeyValue(key=key, value=PB2AnyValue(string_value=str(value)))
                for key, value in (log.attributes or {}).items()
            ],
        )
        req.resource_logs.append(
            PB2ResourceLogs(
                scope_logs=[PB2ScopeLogs(log_records=[log_record])],
            )
        )
    return req


def encode_log_record(log_record: MiniLogRecord) -> PB2LogRecord:
    # Basic encoding logic for a log record
    return PB2LogRecord(
        time_unix_nano=log_record.timestamp or 0,
        severity_number=log_record.severity_number.value if log_record.severity_number else 0,
        severity_text=log_record.severity_text or "",
        body=PB2AnyValue(string_value=str(log_record.body) if log_record.body else ""),
        attributes=[
            PB2KeyValue(key=key, value=PB2AnyValue(string_value=str(value)))
            for key, value in (log_record.attributes or {}).items()
        ],
    )
