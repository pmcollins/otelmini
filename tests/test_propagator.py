"""Tests for W3C TraceContext propagator."""

import pytest
from opentelemetry import trace
from opentelemetry.trace import SpanContext, TraceFlags, NonRecordingSpan

from otelmini.propagator import (
    TraceContextPropagator,
    _format_traceparent,
    _parse_traceparent,
    TRACEPARENT_HEADER,
)


class TestFormatTraceparent:
    def test_basic_format(self):
        sc = SpanContext(
            trace_id=0x4BF92F3577B34DA6A3CE929D0E0E4736,
            span_id=0x00F067AA0BA902B7,
            is_remote=False,
            trace_flags=TraceFlags.SAMPLED,
        )
        result = _format_traceparent(sc)
        assert result == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    def test_unsampled(self):
        sc = SpanContext(
            trace_id=0x4BF92F3577B34DA6A3CE929D0E0E4736,
            span_id=0x00F067AA0BA902B7,
            is_remote=False,
            trace_flags=TraceFlags.DEFAULT,
        )
        result = _format_traceparent(sc)
        assert result == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00"

    def test_small_ids_are_zero_padded(self):
        sc = SpanContext(
            trace_id=0x123,
            span_id=0x456,
            is_remote=False,
            trace_flags=TraceFlags.SAMPLED,
        )
        result = _format_traceparent(sc)
        assert result == "00-00000000000000000000000000000123-0000000000000456-01"


class TestParseTraceparent:
    def test_valid_sampled(self):
        sc = _parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        assert sc is not None
        assert sc.trace_id == 0x4BF92F3577B34DA6A3CE929D0E0E4736
        assert sc.span_id == 0x00F067AA0BA902B7
        assert sc.trace_flags == TraceFlags.SAMPLED
        assert sc.is_remote is True

    def test_valid_unsampled(self):
        sc = _parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00")
        assert sc is not None
        assert sc.trace_flags == TraceFlags.DEFAULT

    def test_uppercase_is_valid(self):
        sc = _parse_traceparent("00-4BF92F3577B34DA6A3CE929D0E0E4736-00F067AA0BA902B7-01")
        assert sc is not None
        assert sc.trace_id == 0x4BF92F3577B34DA6A3CE929D0E0E4736

    def test_whitespace_is_trimmed(self):
        sc = _parse_traceparent("  00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01  ")
        assert sc is not None

    def test_invalid_version_ff(self):
        sc = _parse_traceparent("ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        assert sc is None

    def test_future_version_is_accepted(self):
        # Per spec, unknown versions should be accepted if format matches
        sc = _parse_traceparent("01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        assert sc is not None

    def test_invalid_all_zeros_trace_id(self):
        sc = _parse_traceparent("00-00000000000000000000000000000000-00f067aa0ba902b7-01")
        assert sc is None

    def test_invalid_all_zeros_span_id(self):
        sc = _parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01")
        assert sc is None

    def test_invalid_short_trace_id(self):
        sc = _parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e473-00f067aa0ba902b7-01")
        assert sc is None

    def test_invalid_short_span_id(self):
        sc = _parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b-01")
        assert sc is None

    def test_invalid_missing_parts(self):
        sc = _parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736")
        assert sc is None

    def test_invalid_empty(self):
        sc = _parse_traceparent("")
        assert sc is None

    def test_invalid_non_hex(self):
        sc = _parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e473g-00f067aa0ba902b7-01")
        assert sc is None


class TestTraceContextPropagator:
    def test_fields(self):
        propagator = TraceContextPropagator()
        assert "traceparent" in propagator.fields
        assert "tracestate" in propagator.fields

    def test_inject_with_valid_span(self):
        propagator = TraceContextPropagator()
        carrier = {}

        sc = SpanContext(
            trace_id=0x4BF92F3577B34DA6A3CE929D0E0E4736,
            span_id=0x00F067AA0BA902B7,
            is_remote=False,
            trace_flags=TraceFlags.SAMPLED,
        )
        span = NonRecordingSpan(sc)
        ctx = trace.set_span_in_context(span)

        propagator.inject(carrier, context=ctx)

        assert carrier[TRACEPARENT_HEADER] == "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    def test_inject_with_invalid_span_does_nothing(self):
        propagator = TraceContextPropagator()
        carrier = {}

        # No span in context - should not inject
        propagator.inject(carrier)

        assert TRACEPARENT_HEADER not in carrier

    def test_extract_valid_traceparent(self):
        propagator = TraceContextPropagator()
        carrier = {
            TRACEPARENT_HEADER: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }

        ctx = propagator.extract(carrier)

        span = trace.get_current_span(ctx)
        sc = span.get_span_context()
        assert sc.is_valid
        assert sc.trace_id == 0x4BF92F3577B34DA6A3CE929D0E0E4736
        assert sc.span_id == 0x00F067AA0BA902B7
        assert sc.trace_flags == TraceFlags.SAMPLED
        assert sc.is_remote is True

    def test_extract_missing_header_returns_original_context(self):
        propagator = TraceContextPropagator()
        carrier = {}

        ctx = propagator.extract(carrier)

        span = trace.get_current_span(ctx)
        assert not span.get_span_context().is_valid

    def test_extract_invalid_header_returns_original_context(self):
        propagator = TraceContextPropagator()
        carrier = {TRACEPARENT_HEADER: "invalid"}

        ctx = propagator.extract(carrier)

        span = trace.get_current_span(ctx)
        assert not span.get_span_context().is_valid

    def test_extract_list_value(self):
        """Some HTTP frameworks return header values as lists."""
        propagator = TraceContextPropagator()
        carrier = {
            TRACEPARENT_HEADER: ["00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"]
        }

        # Use a custom getter that returns the list directly
        from opentelemetry.propagators.textmap import Getter

        class ListGetter(Getter):
            def get(self, carrier, key):
                return carrier.get(key)

            def keys(self, carrier):
                return list(carrier.keys())

        ctx = propagator.extract(carrier, getter=ListGetter())

        span = trace.get_current_span(ctx)
        sc = span.get_span_context()
        assert sc.is_valid

    def test_roundtrip(self):
        """Test that inject -> extract preserves trace context."""
        propagator = TraceContextPropagator()

        # Create original span context
        original_sc = SpanContext(
            trace_id=0x4BF92F3577B34DA6A3CE929D0E0E4736,
            span_id=0x00F067AA0BA902B7,
            is_remote=False,
            trace_flags=TraceFlags.SAMPLED,
        )
        span = NonRecordingSpan(original_sc)
        ctx = trace.set_span_in_context(span)

        # Inject into carrier
        carrier = {}
        propagator.inject(carrier, context=ctx)

        # Extract from carrier
        extracted_ctx = propagator.extract(carrier)
        extracted_sc = trace.get_current_span(extracted_ctx).get_span_context()

        # Verify roundtrip
        assert extracted_sc.trace_id == original_sc.trace_id
        assert extracted_sc.span_id == original_sc.span_id
        assert extracted_sc.trace_flags == original_sc.trace_flags
        assert extracted_sc.is_remote is True  # Extracted contexts are always remote
