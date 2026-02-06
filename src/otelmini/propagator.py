"""W3C TraceContext propagator for distributed tracing.

Implements the W3C Trace Context specification for propagating trace context
across service boundaries via HTTP headers.

Spec: https://www.w3.org/TR/trace-context/
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional, Set

from opentelemetry import trace
from opentelemetry.context import Context, get_current, set_value
from opentelemetry.propagators.textmap import (
    CarrierT,
    Getter,
    Setter,
    TextMapPropagator,
    default_getter,
    default_setter,
)
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

if TYPE_CHECKING:
    pass

TRACEPARENT_HEADER = "traceparent"
TRACESTATE_HEADER = "tracestate"

# traceparent format: {version}-{trace_id}-{span_id}-{trace_flags}
# Example: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
_TRACEPARENT_REGEX = re.compile(
    r"^(?P<version>[0-9a-f]{2})-"
    r"(?P<trace_id>[0-9a-f]{32})-"
    r"(?P<span_id>[0-9a-f]{16})-"
    r"(?P<trace_flags>[0-9a-f]{2})$"
)

_SPAN_CONTEXT_KEY = "mini-propagator-span-context"


class TraceContextPropagator(TextMapPropagator):
    """Propagator implementing W3C TraceContext format.

    Injects and extracts trace context via the 'traceparent' header.
    """

    @property
    def fields(self) -> Set[str]:
        return {TRACEPARENT_HEADER, TRACESTATE_HEADER}

    def inject(
        self,
        carrier: CarrierT,
        context: Optional[Context] = None,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        """Inject trace context into carrier (e.g., HTTP headers).

        Args:
            carrier: The carrier to inject into (dict-like for headers)
            context: The context to read span from, or current context if None
            setter: How to set values in the carrier
        """
        span = trace.get_current_span(context)
        span_context = span.get_span_context()

        if not span_context.is_valid:
            return

        traceparent = _format_traceparent(span_context)
        setter.set(carrier, TRACEPARENT_HEADER, traceparent)

    def extract(
        self,
        carrier: CarrierT,
        context: Optional[Context] = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> Context:
        """Extract trace context from carrier (e.g., HTTP headers).

        Args:
            carrier: The carrier to extract from (dict-like for headers)
            context: The context to add span to, or current context if None
            getter: How to get values from the carrier

        Returns:
            A new Context with the extracted span context, or the original
            context if no valid traceparent header is found.
        """
        if context is None:
            context = get_current()

        traceparent = getter.get(carrier, TRACEPARENT_HEADER)
        if traceparent is None:
            return context

        # Handle list return from some getter implementations
        if isinstance(traceparent, list):
            if not traceparent:
                return context
            traceparent = traceparent[0]

        span_context = _parse_traceparent(traceparent)
        if span_context is None:
            return context

        # Create a non-recording span to carry the context
        span = NonRecordingSpan(span_context)
        return trace.set_span_in_context(span, context)


def _format_traceparent(span_context: SpanContext) -> str:
    """Format a SpanContext as a traceparent header value."""
    return f"00-{span_context.trace_id:032x}-{span_context.span_id:016x}-{span_context.trace_flags:02x}"


def _parse_traceparent(traceparent: str) -> Optional[SpanContext]:
    """Parse a traceparent header value into a SpanContext.

    Returns None if the header is invalid.
    """
    match = _TRACEPARENT_REGEX.match(traceparent.strip().lower())
    if not match:
        return None

    version = match.group("version")
    trace_id_hex = match.group("trace_id")
    span_id_hex = match.group("span_id")
    trace_flags_hex = match.group("trace_flags")

    # Version 00 is the only supported version
    # But per spec, unknown versions should be accepted if format is valid
    if version == "ff":
        return None

    trace_id = int(trace_id_hex, 16)
    span_id = int(span_id_hex, 16)
    trace_flags = TraceFlags(int(trace_flags_hex, 16))

    # Invalid if trace_id or span_id is all zeros
    if trace_id == 0 or span_id == 0:
        return None

    return SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=True,
        trace_flags=trace_flags,
    )
