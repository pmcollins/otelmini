from __future__ import annotations

import logging
import time
from typing import Any, Callable, Generic, Sequence, TypeVar, Optional

from grpc import RpcError, insecure_channel

from otelmini._tracelib import ExponentialBackoff

_logger = logging.getLogger(__name__)

# Generic type for different request types
R = TypeVar('R')
# Generic type for different response types
S = TypeVar('S')


class GrpcExporter(Generic[R, S]):
    """
    A generic gRPC exporter that can be used for different signal types (traces, metrics, logs).
    
    This class handles the common functionality of connecting to a gRPC endpoint,
    exporting data, handling errors, and retrying with backoff.
    
    Type parameters:
        R: The type of request to send (e.g., ExportTraceServiceRequest)
        S: The type of response received (e.g., ExportTraceServiceResponse)
    """
    
    def __init__(
        self, 
        addr: str = "127.0.0.1:4317", 
        max_retries: int = 3, 
        channel_provider: Callable[[], Any] = None,
        sleep: Callable[[float], None] = time.sleep,
        stub_class: Any = None,
        response_handler: Callable[[S], None] = None,
        success_result: Any = None,
        failure_result: Any = None
    ):
        """
        Initialize the gRPC exporter.
        
        Args:
            addr: The address of the gRPC endpoint
            max_retries: Maximum number of retry attempts
            channel_provider: A function that returns a gRPC channel
            sleep: A function used for sleeping between retries
            stub_class: The gRPC stub class to use
            response_handler: A function that handles the response from the gRPC endpoint
            success_result: The result to return on successful export
            failure_result: The result to return on failed export
        """
        self.addr = addr
        self.channel_provider = channel_provider if channel_provider else lambda: insecure_channel(addr)
        self.stub_class = stub_class
        self.response_handler = response_handler if response_handler else lambda _: None
        self.success_result = success_result
        self.failure_result = failure_result
        self._connect()
        self.backoff = ExponentialBackoff(max_retries, exceptions=(RpcError,), sleep=sleep)
    
    def export_request(self, req: R) -> Any:
        """
        Export a request to the gRPC endpoint with retry logic.
        
        Args:
            req: The request to export
            
        Returns:
            The result of the export operation
        """
        try:
            resp = self.backoff.retry(SingleReqExporter(self, req).export)
            if self.response_handler:
                self.response_handler(resp)
            return self.success_result
        except ExponentialBackoff.MaxAttemptsError:
            return self.failure_result
    
    def export_single_request(self, req: R) -> S:
        """
        Export a single request to the gRPC endpoint.
        
        Args:
            req: The request to export
            
        Returns:
            The response from the gRPC endpoint
            
        Raises:
            RpcError: If the export fails
        """
        try:
            return self.client.Export(req)
        except RpcError as e:
            self._handle_export_failure(e)
            raise
    
    def _handle_export_failure(self, e: RpcError) -> None:
        """
        Handle an export failure.
        
        Args:
            e: The RpcError that occurred
        """
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
        """
        Connect to the gRPC endpoint.
        """
        if not self.stub_class:
            raise ValueError("Stub class not provided")
            
        self.channel = self.channel_provider()
        self.client = self.stub_class(self.channel)
    
    def shutdown(self) -> None:
        """
        Shutdown the exporter.
        """
        # causes no network transmission
        self.channel.close()
    
    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002
        """
        Force flush any pending exports.
        
        Args:
            timeout_millis: The timeout in milliseconds
            
        Returns:
            Whether the flush was successful
        """
        return False


class SingleReqExporter:
    """
    A helper class for exporting a single request.
    """
    
    def __init__(self, exporter: GrpcExporter, req: Any):
        """
        Initialize the single request exporter.
        
        Args:
            exporter: The exporter to use
            req: The request to export
        """
        self.exporter = exporter
        self.req = req
    
    def export(self) -> Any:
        """
        Export the request.
        
        Returns:
            The response from the gRPC endpoint
        """
        return self.exporter.export_single_request(self.req) 