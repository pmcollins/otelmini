"""W3C TraceContext and Baggage propagators for distributed tracing.

Implements the W3C Trace Context and Baggage specifications for propagating
trace context and application-defined key-value pairs across service boundaries.

Specs:
- https://www.w3.org/TR/trace-context/
- https://www.w3.org/TR/baggage/
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Iterable, Optional, Set
from urllib.parse import quote_plus, unquote_plus

from opentelemetry import baggage, trace
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
BAGGAGE_HEADER = "baggage"

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


class BaggagePropagator(TextMapPropagator):
    """Propagator implementing W3C Baggage format.

    Injects and extracts baggage (key-value pairs) via the 'baggage' header.
    """

    # Max header size per W3C spec recommendation
    _MAX_HEADER_LENGTH = 8192
    _MAX_PAIRS = 180
    _MAX_PAIR_LENGTH = 4096

    @property
    def fields(self) -> Set[str]:
        return {BAGGAGE_HEADER}

    def inject(
        self,
        carrier: CarrierT,
        context: Optional[Context] = None,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        """Inject baggage into carrier (e.g., HTTP headers).

        Args:
            carrier: The carrier to inject into (dict-like for headers)
            context: The context to read baggage from, or current context if None
            setter: How to set values in the carrier
        """
        baggage_entries = baggage.get_all(context)
        if not baggage_entries:
            return

        pairs = []
        for key, value in baggage_entries.items():
            encoded_value = quote_plus(str(value))
            pair = f"{key}={encoded_value}"
            if len(pair) <= self._MAX_PAIR_LENGTH:
                pairs.append(pair)
            if len(pairs) >= self._MAX_PAIRS:
                break

        if pairs:
            header_value = ",".join(pairs)
            if len(header_value) <= self._MAX_HEADER_LENGTH:
                setter.set(carrier, BAGGAGE_HEADER, header_value)

    def extract(
        self,
        carrier: CarrierT,
        context: Optional[Context] = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> Context:
        """Extract baggage from carrier (e.g., HTTP headers).

        Args:
            carrier: The carrier to extract from (dict-like for headers)
            context: The context to add baggage to, or current context if None
            getter: How to get values from the carrier

        Returns:
            A new Context with the extracted baggage, or the original
            context if no valid baggage header is found.
        """
        if context is None:
            context = get_current()

        header_value = getter.get(carrier, BAGGAGE_HEADER)
        if header_value is None:
            return context

        # Handle list return from some getter implementations
        if isinstance(header_value, list):
            if not header_value:
                return context
            header_value = header_value[0]

        # Parse baggage entries
        for entry in header_value.split(","):
            entry = entry.strip()
            if not entry:
                continue

            # Split on first '=' only (value may contain '=')
            if "=" not in entry:
                continue

            key, value = entry.split("=", 1)
            key = key.strip()

            # Strip optional properties (;property=value)
            if ";" in value:
                value = value.split(";", 1)[0]

            value = unquote_plus(value.strip())

            if key:
                context = baggage.set_baggage(key, value, context)

        return context


class CompositePropagator(TextMapPropagator):
    """Combines multiple propagators into one.

    Useful for propagating both trace context and baggage together.
    """

    def __init__(self, propagators: Iterable[TextMapPropagator]):
        self._propagators = list(propagators)

    @property
    def fields(self) -> Set[str]:
        fields: Set[str] = set()
        for propagator in self._propagators:
            fields.update(propagator.fields)
        return fields

    def inject(
        self,
        carrier: CarrierT,
        context: Optional[Context] = None,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        for propagator in self._propagators:
            propagator.inject(carrier, context, setter)

    def extract(
        self,
        carrier: CarrierT,
        context: Optional[Context] = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> Context:
        for propagator in self._propagators:
            context = propagator.extract(carrier, context, getter)
        return context


def get_default_propagator() -> CompositePropagator:
    """Return a propagator that handles both TraceContext and Baggage."""
    return CompositePropagator([TraceContextPropagator(), BaggagePropagator()])
