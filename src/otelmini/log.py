from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Sequence

from opentelemetry._logs import Logger as ApiLogger
from opentelemetry._logs import LoggerProvider as ApiLoggerProvider
from opentelemetry._logs import LogRecord as ApiLogRecord
from opentelemetry._logs import SeverityNumber
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest as PB2ExportLogsServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue as PB2AnyValue
from opentelemetry.proto.common.v1.common_pb2 import KeyValue as PB2KeyValue
from opentelemetry.proto.logs.v1.logs_pb2 import LogRecord as PB2LogRecord
from opentelemetry.proto.logs.v1.logs_pb2 import ResourceLogs as PB2ResourceLogs
from opentelemetry.proto.logs.v1.logs_pb2 import ScopeLogs as PB2ScopeLogs

from otelmini.grpc import GrpcExporter, GrpcExportResult
from otelmini.processor import BatchProcessor, Exporter, Processor

if TYPE_CHECKING:
    from opentelemetry.trace import TraceFlags
    from opentelemetry.util.types import Attributes
else:
    TraceFlags = Any
    Attributes = Any


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
    def export(self, logs: Sequence[MiniLogRecord]) -> GrpcExportResult:
        pass

    @abstractmethod
    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        pass

    @abstractmethod
    def shutdown(self, timeout_millis: Optional[int] = None) -> None:
        pass


class ConsoleLogExporter(LogRecordExporter):
    def export(self, logs: Sequence[MiniLogRecord]) -> GrpcExportResult:
        try:
            for log in logs:
                print(f"log: {log}")  # noqa: T201
        except Exception as e:
            raise LogExportError from e
        else:
            return GrpcExportResult.SUCCESS

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        pass

    def shutdown(self, timeout_millis: Optional[int] = None) -> None:
        pass


class GrpcLogExporterImportError(ImportError):
    def __init__(self, message: str = "The opentelemetry-proto package is required for GrpcLogExporter. Install it with: pip install otelmini[grpc]"):
        super().__init__(message)


class GrpcLogExporter(LogRecordExporter):
    def __init__(self, addr="127.0.0.1:4317", max_retries=3, channel_provider=None, sleep=time.sleep):
        try:
            from opentelemetry.proto.collector.logs.v1.logs_service_pb2_grpc import LogsServiceStub
        except ImportError as err:
            raise GrpcLogExporterImportError from err

        self._exporter = GrpcExporter(
            addr=addr,
            max_retries=max_retries,
            channel_provider=channel_provider,
            sleep=sleep,
            stub_class=LogsServiceStub,
            response_handler=handle_log_response,
        )

    def export(self, logs: Sequence[MiniLogRecord]) -> GrpcExportResult:
        req = mk_log_request(logs)
        return self._exporter.export_request(req)

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        return self._exporter.force_flush(timeout_millis)

    def shutdown(self, timeout_millis: Optional[int] = None) -> None:
        self._exporter.shutdown()


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
        try:
            pylog_mini_log_record = _pylog_to_minilog(pylog_record)
            for processor in self._logger_provider.processors:
                processor.on_end(pylog_mini_log_record)
        except Exception as e:
            print(f"error emitting logs: {e}")


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
            'filename': pylog_record.filename,
            'funcName': pylog_record.funcName,
            'lineno': pylog_record.lineno,
            'module': pylog_record.module,
            'name': pylog_record.name,
            'pathname': pylog_record.pathname,
            'process': pylog_record.process,
            'processName': pylog_record.processName,
            'thread': pylog_record.thread,
            'threadName': pylog_record.threadName,
        }
    )


class LoggerProvider(ApiLoggerProvider):
    def __init__(self, processors: Optional[Sequence[LogRecordProcessor]] = None):
        self.processors = list(processors) if processors else []

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

    def add_log_record_processor(self, processor: LogRecordProcessor) -> None:
        self.processors.append(processor)

    def shutdown(self) -> None:
        for processor in self.processors:
            processor.shutdown()

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        return all(processor.force_flush(timeout_millis) for processor in self.processors)


class LogRecordProcessor(Processor[MiniLogRecord], ABC):
    @abstractmethod
    def on_start(self, log_record: MiniLogRecord) -> None:
        pass

    @abstractmethod
    def on_end(self, log_record: MiniLogRecord) -> None:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass

    @abstractmethod
    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        pass


class BatchLogRecordProcessor(LogRecordProcessor):
    def __init__(self, exporter: LogRecordExporter, batch_size: int = 512, export_interval_millis: int = 5000):
        self._processor = BatchProcessor(
            exporter=exporter,
            batch_size=batch_size,
            interval_seconds=export_interval_millis / 1000,
        )

    def on_start(self, log_record: MiniLogRecord) -> None:
        self._processor.on_start(log_record)

    def on_end(self, log_record: MiniLogRecord) -> None:
        self._processor.on_end(log_record)

    def shutdown(self) -> None:
        self._processor.shutdown()

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        return self._processor.force_flush(timeout_millis)


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


class OtelBridgeHandler(logging.Handler):
    def __init__(self, logger_provider, level=logging.NOTSET):
        super().__init__(level=level)
        self.logger_provider = logger_provider

    def emit(self, record: logging.LogRecord):
        try:
            logger = self.logger_provider.get_logger(record.name)
            logger.emit(record)
        except Exception as ex:
            print(f"error emitting log record: {ex}")
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
                scope_logs=[
                    PB2ScopeLogs(
                        log_records=[log_record]
                    )
                ],
            )
        )
    return req


def handle_log_response(resp):
    if resp.HasField("partial_success") and resp.partial_success:
        ps = resp.partial_success
        msg = f"partial success: rejected_log_records: [{ps.rejected_log_records_count}], error_message: [{ps.error_message}]"
        logging.warning(msg)


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
