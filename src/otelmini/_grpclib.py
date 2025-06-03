from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from grpc import RpcError, StatusCode, insecure_channel
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

from otelmini._lib import ExportResult, Retrier, RetrierResult, SingleAttemptResult

_logger = logging.getLogger(__package__)


class GrpcConnectionManager:
    def __init__(
        self,
        stub_class,
        addr: str = "127.0.0.1:4317",
        channel_provider: Optional[Callable[[], Any]] = None,
    ):
        self.channel_provider = channel_provider if channel_provider else lambda: insecure_channel(addr)
        self.stub_class = stub_class
        self.channel = self.channel_provider()
        self.client = self.stub_class(self.channel)

    def export(self, req: Any) -> Any:
        return self.client.Export(req)

    def handle_retryable_error(self):
        self.close_channel()
        self.reconnect()

    def close_channel(self):
        self.channel.close()

    def reconnect(self):
        self.channel = self.channel_provider()
        self.client = self.stub_class(self.channel)


class GrpcExporter:
    class SingleGrpcAttempt:
        def __init__(self, response_class, connection_manager: GrpcConnectionManager, req: Any):
            self.response_class = response_class
            self.connection_manager = connection_manager
            self.req = req

        def export(self) -> Any:
            try:
                response = self.connection_manager.export(self.req)

                if isinstance(response, self.response_class):
                    return SingleAttemptResult.SUCCESS
                return SingleAttemptResult.FAILURE
            except RpcError as e:
                if _is_retryable(e.code()):
                    self.connection_manager.handle_retryable_error()
                    return SingleAttemptResult.RETRY
                return SingleAttemptResult.FAILURE

    def __init__(
        self,
        response_class,
        addr: str = "127.0.0.1:4317",
        max_retries: int = 3,
        channel_provider: Optional[Callable[[], Any]] = None,
        sleep: Callable[[float], None] = time.sleep,
        stub_class: Any = None,
    ):
        self.response_class = response_class
        self.addr = addr
        self.connection_manager = GrpcConnectionManager(stub_class, addr, channel_provider)
        self.retrier = Retrier(max_retries, sleep=sleep)

    def export(self, req) -> Any:
        single_req_exporter = GrpcExporter.SingleGrpcAttempt(self.response_class, self.connection_manager, req)
        retry_result = self.retrier.retry(single_req_exporter.export)
        return ExportResult.SUCCESS if retry_result == RetrierResult.SUCCESS else ExportResult.FAILURE

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return False

    def shutdown(self) -> None:
        self.connection_manager.close_channel()


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
