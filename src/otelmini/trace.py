from __future__ import annotations

import logging
import random
import typing
from typing import TYPE_CHECKING, Iterator, Optional, Sequence

from opentelemetry import trace
from opentelemetry.trace import Span as ApiSpan
from opentelemetry.trace import SpanKind, Tracer, TracerProvider, _Links
from opentelemetry.trace.span import SpanContext
from opentelemetry.util._decorator import _agnosticcontextmanager

from otelmini._lib import Exporter, ExportResult, _HttpExporter
from otelmini.encode import encode_trace_request
from otelmini.types import InstrumentationScope, MiniSpan, Resource

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.util import types

    from otelmini.processor import Processor

_pylogger = logging.getLogger(__package__)


def _generate_trace_id() -> int:
    """Generate a random 128-bit trace ID."""
    return random.getrandbits(128)


def _generate_span_id() -> int:
    """Generate a random 64-bit span ID."""
    return random.getrandbits(64)


class MiniTracerProvider(TracerProvider):
    def __init__(self, span_processor=None, resource: Resource = None):
        self.span_processor = span_processor
        self.resource = resource or Resource()

    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: typing.Optional[str] = None,
        schema_url: typing.Optional[str] = None,
        attributes: typing.Optional[types.Attributes] = None,
    ) -> MiniTracer:
        scope = InstrumentationScope(instrumenting_module_name, instrumenting_library_version)
        return MiniTracer(self.span_processor, self.resource, scope)

    def shutdown(self):
        if self.span_processor:
            self.span_processor.shutdown()


class MiniTracer(Tracer):
    def __init__(self, span_processor: Processor[MiniSpan], resource: Resource, scope: InstrumentationScope):
        self.span_processor = span_processor
        self.resource = resource
        self.scope = scope

    def start_span(
        self,
        name: str,
        context: Optional[Context] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: types.Attributes = None,
        links: _Links = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,  # noqa: FBT001, FBT002
        set_status_on_exception: bool = True,  # noqa: FBT001, FBT002
    ) -> ApiSpan:
        parent_span_context = trace.get_current_span().get_span_context()
        if parent_span_context.is_valid:
            trace_id = parent_span_context.trace_id
            parent_span_id = parent_span_context.span_id
        else:
            trace_id = _generate_trace_id()
            parent_span_id = None
        span_id = _generate_span_id()
        span_context = SpanContext(trace_id, span_id, is_remote=False)
        span = MiniSpan(
            name, span_context, self.resource, self.scope, self.span_processor.on_end,
            parent_span_id=parent_span_id,
        )
        self.span_processor.on_start(span)
        return span

    @_agnosticcontextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Optional[Context] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: types.Attributes = None,
        links: _Links = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,  # noqa: FBT001, FBT002
        set_status_on_exception: bool = True,  # noqa: FBT001, FBT002
        end_on_exit: bool = True,  # noqa: FBT001, FBT002
    ) -> Iterator[ApiSpan]:
        span = self.start_span(name, context, kind, attributes, links, start_time, end_on_exit)
        with trace.use_span(span, end_on_exit=True) as active_span:
            yield active_span


class ConsoleSpanExporter(Exporter[MiniSpan]):
    def export(self, items: Sequence[MiniSpan]) -> ExportResult:
        print(encode_trace_request(items))  # noqa: T201
        return ExportResult.SUCCESS


class HttpSpanExporter(Exporter[MiniSpan]):
    def __init__(self, endpoint="http://localhost:4318/v1/traces", timeout=30):
        self._exporter = _HttpExporter(endpoint, timeout)

    def export(self, items: Sequence[MiniSpan]) -> ExportResult:
        data = encode_trace_request(items)
        return self._exporter.export(data)
