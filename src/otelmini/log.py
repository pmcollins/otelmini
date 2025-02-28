from __future__ import annotations

import logging
import sys
import json
from enum import Enum
from typing import Any, Optional, Sequence
import threading
import time

from opentelemetry._logs import Logger as ApiLogger
from opentelemetry._logs import LoggerProvider as ApiLoggerProvider
from opentelemetry._logs import LogRecord as ApiLogRecord
from opentelemetry._logs import SeverityNumber
from opentelemetry.trace import TraceFlags
from opentelemetry.util.types import Attributes


class LogExportResult(Enum):
    SUCCESS = 0
    FAILURE = 1


class LogRecordExporter:
    def export(self, logs: Sequence[LogRecord], **kwargs) -> LogExportResult:
        return LogExportResult.SUCCESS

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        return True

    def shutdown(self, timeout_millis: Optional[int] = None) -> None:
        pass


class ConsoleLogExporter(LogRecordExporter):
    def export(self, logs: Sequence[LogRecord], **kwargs) -> LogExportResult:
        try:
            for log in logs:
                log_dict = {
                    "timestamp": log.timestamp,
                    "observed_timestamp": log.observed_timestamp,
                    "trace_id": f"{log.trace_id:032x}" if log.trace_id else None,
                    "span_id": f"{log.span_id:016x}" if log.span_id else None,
                    "trace_flags": str(log.trace_flags) if log.trace_flags else None,
                    "severity_text": log.severity_text,
                    "severity_number": log.severity_number.name if log.severity_number else None,
                    "body": log.body,
                    "attributes": log.attributes,
                }
                print(json.dumps(log_dict, default=str))
            return LogExportResult.SUCCESS
        except Exception as e:
            print(f"Error exporting logs: {e}")
            return LogExportResult.FAILURE


class LogRecord(ApiLogRecord):
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
            attributes=attributes,
        )


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

    def emit(self, record: ApiLogRecord) -> None:
        for processor in self._logger_provider.processors:
            processor.on_emit(record)


class LoggerProvider(ApiLoggerProvider):
    def __init__(self, processors: Optional[Sequence[LogRecordProcessor]] = None):
        self.processors = list(processors) if processors else []

    def get_logger(
        self, name: str, version: Optional[str] = None, schema_url: Optional[str] = None,
        attributes: Optional[Attributes] = None
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


class LogRecordProcessor:
    def __init__(self):
        pass

    def on_emit(self, log_record: LogRecord) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        return True


class ExportingLogRecordProcessor(LogRecordProcessor):
    def __init__(self, exporter: LogRecordExporter):
        super().__init__()
        self._exporter = exporter
        self._logs_buffer = []

    def on_emit(self, log_record: LogRecord) -> None:
        self._exporter.export([log_record])

    def shutdown(self) -> None:
        self.force_flush()
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        return self._exporter.force_flush(timeout_millis)


class BatchLogRecordProcessor(LogRecordProcessor):
    def __init__(self, exporter: LogRecordExporter, max_queue_size: int = 2048,
                 batch_size: int = 512, export_interval_millis: int = 5000):
        super().__init__()
        self._exporter = exporter
        self._max_queue_size = max_queue_size
        self._batch_size = batch_size
        self._export_interval_millis = export_interval_millis
        self._logs_buffer = []
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._export_thread = threading.Thread(target=self._export_worker, daemon=True)
        self._shutdown = False
        self._export_thread.start()

    def on_emit(self, log_record: LogRecord) -> None:
        with self._lock:
            if len(self._logs_buffer) < self._max_queue_size:
                self._logs_buffer.append(log_record)
                self._condition.notify()

    def _export_worker(self) -> None:
        while not self._shutdown:
            with self._condition:
                if not self._logs_buffer:
                    self._condition.wait(self._export_interval_millis / 1000)
                    if not self._logs_buffer and not self._shutdown:
                        continue

                batch = self._logs_buffer[:self._batch_size]
                self._logs_buffer = self._logs_buffer[self._batch_size:]

            if batch:
                self._exporter.export(batch)

    def shutdown(self) -> None:
        with self._condition:
            self._shutdown = True
            self._condition.notify()

        self._export_thread.join()
        self.force_flush()
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        with self._lock:
            batch = self._logs_buffer
            self._logs_buffer = []

        if batch:
            self._exporter.export(batch)

        return self._exporter.force_flush(timeout_millis)


def _get_severity_number(levelno):
    if levelno >= logging.CRITICAL:
        return SeverityNumber.FATAL
    elif levelno >= logging.ERROR:
        return SeverityNumber.ERROR
    elif levelno >= logging.WARNING:
        return SeverityNumber.WARN
    elif levelno >= logging.INFO:
        return SeverityNumber.INFO
    elif levelno >= logging.DEBUG:
        return SeverityNumber.DEBUG
    else:
        return SeverityNumber.TRACE


class OtelBridgeHandler(logging.Handler):
    def __init__(self, level=logging.NOTSET, logger_provider=None):
        super().__init__(level=level)
        provider = logger_provider or LoggerProvider()
        self._logger = provider.get_logger("python.logging")

    def emit(self, record):
        try:
            severity_number = _get_severity_number(record.levelno)

            otel_record = LogRecord(
                timestamp=int(record.created * 1_000_000_000),
                observed_timestamp=int(time.time() * 1_000_000_000),
                severity_text=record.levelname,
                severity_number=severity_number,
                body=record.getMessage(),
                attributes={
                    "logger.name": record.name,
                    "logger.thread_name": record.threadName,
                    "logger.filename": record.filename,
                    "logger.lineno": record.lineno,
                    "logger.pathname": record.pathname,
                    "logger.funcName": record.funcName,
                },
            )

            self._logger.emit(otel_record)
        except Exception:
            self.handleError(record)


def main():
    console_exporter = ConsoleLogExporter()
    batch_processor = BatchLogRecordProcessor(console_exporter)
    logger_provider = LoggerProvider([batch_processor])
    python_logger = logging.getLogger("example")
    python_logger.setLevel(logging.DEBUG)
    otel_handler = OtelBridgeHandler(logger_provider=logger_provider)
    python_logger.addHandler(otel_handler)
    python_logger.debug("This is a debug message")
    python_logger.info("This is an info message")
    python_logger.warning("This is a warning message")
    python_logger.error("This is an error message")
    python_logger.critical("This is a critical message")
    logger_provider.shutdown()


if __name__ == "__main__":
    main()
