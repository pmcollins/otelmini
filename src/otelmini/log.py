from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Sequence

from opentelemetry._logs import Logger as ApiLogger
from opentelemetry._logs import LoggerProvider as ApiLoggerProvider
from opentelemetry._logs import LogRecord as ApiLogRecord
from opentelemetry._logs import SeverityNumber

from otelmini.grpc import GrpcExporter
from otelmini.processor import BatchProcessor, Processor

if TYPE_CHECKING:
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    from opentelemetry.trace import TraceFlags
    from opentelemetry.util.types import Attributes
else:
    TraceFlags = Any
    Attributes = Any


class LogExportResult(Enum):
    SUCCESS = 0
    FAILURE = 1


class LogRecordExporter(ABC):
    @abstractmethod
    def export(self, logs: Sequence[LogRecord]) -> LogExportResult:
        pass

    @abstractmethod
    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        pass

    @abstractmethod
    def shutdown(self, timeout_millis: Optional[int] = None) -> None:
        pass


class ConsoleLogExporter(LogRecordExporter):
    def export(self, logs: Sequence[LogRecord]) -> LogExportResult:
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
                logging.info(json.dumps(log_dict, default=str))
        except Exception:
            logging.exception("Error exporting logs")
            return LogExportResult.FAILURE
        else:
            return LogExportResult.SUCCESS


def mk_log_request(logs: Sequence[LogRecord]) -> ExportLogsServiceRequest:  # noqa: ARG001
    """
    Create a log request from a sequence of log records.
    
    Args:
        logs: The log records to include in the request
        
    Returns:
        An ExportLogsServiceRequest containing the log records
    """
    # This is a placeholder implementation
    # In a real implementation, you would convert the logs to protobuf format
    from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
    from opentelemetry.proto.logs.v1.logs_pb2 import ResourceLogs

    # Create a request with empty resource logs
    # This needs to be implemented properly based on the protobuf definitions
    return ExportLogsServiceRequest(resource_logs=[ResourceLogs()])


def handle_log_response(resp):
    """
    Handle the response from the gRPC endpoint for logs.
    
    Args:
        resp: The response from the gRPC endpoint
    """
    if resp.HasField("partial_success") and resp.partial_success:
        ps = resp.partial_success
        msg = f"partial success: rejected_log_records: [{ps.rejected_log_records_count}], error_message: [{ps.error_message}]"
        logging.warning(msg)


class GrpcLogExporter(LogRecordExporter):
    """
    A gRPC exporter for logs that uses composition with the generic GrpcExporter.
    """
    PROTO_PACKAGE_REQUIRED = "opentelemetry-proto package is required for GrpcLogExporter"

    def __init__(self, addr="127.0.0.1:4317", max_retries=3, channel_provider=None, sleep=time.sleep):
        """
        Initialize the gRPC log exporter.
        
        Args:
            addr: The address of the gRPC endpoint
            max_retries: Maximum number of retry attempts
            channel_provider: A function that returns a gRPC channel
            sleep: A function used for sleeping between retries
        """
        try:
            from opentelemetry.proto.collector.logs.v1.logs_service_pb2_grpc import LogsServiceStub
        except ImportError as err:
            raise ImportError(self.PROTO_PACKAGE_REQUIRED) from err

        self._exporter = GrpcExporter(
            addr=addr,
            max_retries=max_retries,
            channel_provider=channel_provider,
            sleep=sleep,
            stub_class=LogsServiceStub,
            response_handler=handle_log_response,
        )

    def export(self, logs: Sequence[LogRecord]) -> LogExportResult:
        """
        Export logs to the gRPC endpoint.
        
        Args:
            logs: The logs to export
            
        Returns:
            The result of the export operation
        """
        req = mk_log_request(logs)
        return self._exporter.export_request(req)

    def force_flush(self, timeout_millis: Optional[int] = None) -> bool:
        """
        Force flush any pending exports.
        
        Args:
            timeout_millis: The timeout in milliseconds
            
        Returns:
            Whether the flush was successful
        """
        return self._exporter.force_flush(timeout_millis)

    def shutdown(self, timeout_millis: Optional[int] = None) -> None:  # noqa: ARG002
        """
        Shutdown the exporter.
        
        Args:
            timeout_millis: The timeout in milliseconds
        """
        self._exporter.shutdown()


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
            processor.on_end(record)


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


class LogRecordProcessor(Processor[LogRecord], ABC):
    @abstractmethod
    def on_start(self, log_record: LogRecord) -> None:
        pass

    @abstractmethod
    def on_end(self, log_record: LogRecord) -> None:
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

    def on_start(self, log_record: LogRecord) -> None:
        self._processor.on_start(log_record)

    def on_end(self, log_record: LogRecord) -> None:
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

    def emit(self, record):
        try:
            logger = self.logger_provider.get_logger(record.name)
            logger.emit(record)
        except Exception:
            logging.exception("Error emitting log record")
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
