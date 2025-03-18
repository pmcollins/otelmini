from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar

from grpc import RpcError, insecure_channel

from otelmini._tracelib import ExponentialBackoff

_logger = logging.getLogger(__package__)

# Generic type for different request types
R = TypeVar("R")
# Generic type for different response types
S = TypeVar("S")


class GrpcExportResult(Enum):
    FAILURE = 0
    SUCCESS = 1


class GrpcExporter(Generic[R, S]):
    def __init__(
        self,
        addr: str = "127.0.0.1:4317",
        max_retries: int = 3,
        channel_provider: Optional[Callable[[], Any]] = None,
        sleep: Callable[[float], None] = time.sleep,
        stub_class: Optional[Any] = None,
        response_handler: Optional[Callable[[S], None]] = None,
    ):
        self.addr = addr
        self.channel_provider = channel_provider if channel_provider else lambda: insecure_channel(addr)
        self.stub_class = stub_class
        self.response_handler = response_handler if response_handler else lambda _: None
        self._connect()
        self.backoff = ExponentialBackoff(max_retries, exceptions=(RpcError,), sleep=sleep)

    def export_request(self, req: R) -> Any:
        try:
            resp = self.backoff.retry(SingleReqExporter(self, req).export)
            if self.response_handler:
                self.response_handler(resp)
        except ExponentialBackoff.MaxAttemptsError:
            return GrpcExportResult.FAILURE
        else:
            return GrpcExportResult.SUCCESS

    def export_single_request(self, req: R) -> S:
        try:
            return self.client.Export(req)
        except RpcError as e:
            self._handle_export_failure(e)
            raise

    def _handle_export_failure(self, e: RpcError) -> None:
        if hasattr(e, "code") and e.code:
            status = e.code().name  # e.g. "UNAVAILABLE"
            _logger.warning("Rpc error during export: %s", status)
        else:
            _logger.warning("Rpc error during export: %s", e)
        # close the channel, even if not strictly necessary
        self.shutdown()
        # if the export failed (e.g. because the server is unavailable) reconnect
        # otherwise later attempts will continue to fail even when the server comes back up
        self._connect()

    def _connect(self) -> None:
        if not self.stub_class:
            raise ValueError("Stub class not provided")
        self.channel = self.channel_provider()
        self.client = self.stub_class(self.channel)

    def shutdown(self) -> None:
        # causes no network transmission
        self.channel.close()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return False


class SingleReqExporter:
    def __init__(self, exporter: GrpcExporter, req: Any):
        self.exporter = exporter
        self.req = req

    def export(self) -> Any:
        return self.exporter.export_single_request(self.req)
