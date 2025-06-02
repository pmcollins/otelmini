from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from grpc import RpcError, StatusCode, insecure_channel

from otelmini._lib import ExportResult, Retrier, RetrierResult, SingleAttemptResult

_logger = logging.getLogger(__package__)


class GrpcConnectionManager:
    class StubClassRequiredError(ValueError):
        """stub_class must be provided for the first connection"""

    def __init__(
        self,
        addr: str = "127.0.0.1:4317",
        channel_provider: Optional[Callable[[], Any]] = None,
    ):
        self.addr = addr
        self.channel_provider = channel_provider if channel_provider else lambda: insecure_channel(addr)
        self.channel = None
        self.client = None
        self.stub_class = None

    def connect(self, stub_class: Any = None) -> None:
        if stub_class is not None:
            self.stub_class = stub_class
        if self.channel is None:
            self.channel = self.channel_provider()
        if self.stub_class is None:
            raise GrpcConnectionManager.StubClassRequiredError()
        self.client = self.stub_class(self.channel)

    def shutdown(self) -> None:
        if self.channel:
            self.channel.close()
        self.channel = None
        self.client = None

    def export(self, req: Any) -> Any:
        return self.client.Export(req)

    def handle_retryable_error(self):
        self.shutdown()
        self.connect()


class GrpcExporter:
    class SingleGrpcAttempt:
        def __init__(self, connection_manager: GrpcConnectionManager, req: Any):
            self.connection_manager = connection_manager
            self.req = req

        def export(self) -> Any:
            try:
                response = self.connection_manager.export(self.req)
                return self._handle_response(response)
            except RpcError as e:
                if _is_retryable(e.code()):
                    return self._handle_retryable_error(e)
                return SingleAttemptResult.FAILURE

        def _handle_response(self, response: Any) -> SingleAttemptResult:
            from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
            if isinstance(response, ExportTraceServiceResponse):
                return SingleAttemptResult.SUCCESS
            return SingleAttemptResult.FAILURE

        def _handle_retryable_error(self, e: RpcError) -> SingleAttemptResult:
            self.connection_manager.handle_retryable_error()
            return SingleAttemptResult.RETRY

    def __init__(
            self,
            addr: str = "127.0.0.1:4317",
            max_retries: int = 3,
            channel_provider: Optional[Callable[[], Any]] = None,
            sleep: Callable[[float], None] = time.sleep,
            stub_class: Any = None,
    ):
        self.addr = addr
        self.connection_manager = GrpcConnectionManager(addr, channel_provider)
        self.stub_class = stub_class
        if stub_class is not None:
            self.connection_manager.stub_class = stub_class
        self.retrier = Retrier(max_retries, sleep=sleep)

    def connect(self) -> None:
        self.connection_manager.connect(self.stub_class)

    def export(self, req) -> Any:
        # Ensure connection is established with stub_class before exporting
        if self.connection_manager.stub_class is None:
            self.connect()
        single_req_exporter = GrpcExporter.SingleGrpcAttempt(self.connection_manager, req)
        retry_result = self.retrier.retry(single_req_exporter.export)
        return ExportResult.SUCCESS if retry_result == RetrierResult.SUCCESS else ExportResult.FAILURE

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return False

    def reconnect(self, e: RpcError) -> None:
        self.connection_manager.shutdown()
        self.connect()

    def shutdown(self) -> None:
        self.connection_manager.shutdown()


def _is_retryable(status_code: StatusCode):
    return status_code in [
        StatusCode.CANCELLED,
        StatusCode.DEADLINE_EXCEEDED,
        StatusCode.RESOURCE_EXHAUSTED,
        StatusCode.ABORTED,
        StatusCode.OUT_OF_RANGE,
        StatusCode.UNAVAILABLE,
        StatusCode.DATA_LOSS,
    ]
