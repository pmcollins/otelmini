"""Tests for W3C TraceContext and Baggage propagators."""

import pytest
from opentelemetry import baggage, trace
from opentelemetry.trace import SpanContext, TraceFlags, NonRecordingSpan

from otelmini.propagator import (
    BAGGAGE_HEADER,
    TRACEPARENT_HEADER,
    BaggagePropagator,
    CompositePropagator,
    TraceContextPropagator,
    _format_traceparent,
    _parse_traceparent,
    get_default_propagator,
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


class TestBaggagePropagator:
    def test_fields(self):
        propagator = BaggagePropagator()
        assert "baggage" in propagator.fields

    def test_inject_single_entry(self):
        propagator = BaggagePropagator()
        carrier = {}

        ctx = baggage.set_baggage("userId", "alice")

        propagator.inject(carrier, context=ctx)

        assert carrier[BAGGAGE_HEADER] == "userId=alice"

    def test_inject_multiple_entries(self):
        propagator = BaggagePropagator()
        carrier = {}

        ctx = baggage.set_baggage("userId", "alice")
        ctx = baggage.set_baggage("region", "us-east", context=ctx)

        propagator.inject(carrier, context=ctx)

        # Order may vary, so check both entries are present
        header = carrier[BAGGAGE_HEADER]
        assert "userId=alice" in header
        assert "region=us-east" in header
        assert "," in header

    def test_inject_url_encodes_values(self):
        propagator = BaggagePropagator()
        carrier = {}

        ctx = baggage.set_baggage("query", "hello world")

        propagator.inject(carrier, context=ctx)

        assert carrier[BAGGAGE_HEADER] == "query=hello+world"

    def test_inject_special_characters(self):
        propagator = BaggagePropagator()
        carrier = {}

        ctx = baggage.set_baggage("data", "a=b&c=d")

        propagator.inject(carrier, context=ctx)

        assert carrier[BAGGAGE_HEADER] == "data=a%3Db%26c%3Dd"

    def test_inject_empty_baggage_does_nothing(self):
        propagator = BaggagePropagator()
        carrier = {}

        propagator.inject(carrier)

        assert BAGGAGE_HEADER not in carrier

    def test_extract_single_entry(self):
        propagator = BaggagePropagator()
        carrier = {BAGGAGE_HEADER: "userId=alice"}

        ctx = propagator.extract(carrier)

        assert baggage.get_baggage("userId", ctx) == "alice"

    def test_extract_multiple_entries(self):
        propagator = BaggagePropagator()
        carrier = {BAGGAGE_HEADER: "userId=alice,region=us-east"}

        ctx = propagator.extract(carrier)

        assert baggage.get_baggage("userId", ctx) == "alice"
        assert baggage.get_baggage("region", ctx) == "us-east"

    def test_extract_url_decodes_values(self):
        propagator = BaggagePropagator()
        carrier = {BAGGAGE_HEADER: "query=hello+world"}

        ctx = propagator.extract(carrier)

        assert baggage.get_baggage("query", ctx) == "hello world"

    def test_extract_special_characters(self):
        propagator = BaggagePropagator()
        carrier = {BAGGAGE_HEADER: "data=a%3Db%26c%3Dd"}

        ctx = propagator.extract(carrier)

        assert baggage.get_baggage("data", ctx) == "a=b&c=d"

    def test_extract_with_properties_strips_them(self):
        """Properties after semicolon should be stripped."""
        propagator = BaggagePropagator()
        carrier = {BAGGAGE_HEADER: "userId=alice;property=value"}

        ctx = propagator.extract(carrier)

        assert baggage.get_baggage("userId", ctx) == "alice"

    def test_extract_whitespace_is_trimmed(self):
        propagator = BaggagePropagator()
        carrier = {BAGGAGE_HEADER: " userId = alice , region = us-east "}

        ctx = propagator.extract(carrier)

        assert baggage.get_baggage("userId", ctx) == "alice"
        assert baggage.get_baggage("region", ctx) == "us-east"

    def test_extract_missing_header_returns_original_context(self):
        propagator = BaggagePropagator()
        carrier = {}

        ctx = propagator.extract(carrier)

        assert baggage.get_all(ctx) == {}

    def test_extract_empty_entries_are_skipped(self):
        propagator = BaggagePropagator()
        carrier = {BAGGAGE_HEADER: "userId=alice,,region=us-east"}

        ctx = propagator.extract(carrier)

        assert baggage.get_baggage("userId", ctx) == "alice"
        assert baggage.get_baggage("region", ctx) == "us-east"

    def test_extract_entries_without_equals_are_skipped(self):
        propagator = BaggagePropagator()
        carrier = {BAGGAGE_HEADER: "userId=alice,invalid,region=us-east"}

        ctx = propagator.extract(carrier)

        assert baggage.get_baggage("userId", ctx) == "alice"
        assert baggage.get_baggage("region", ctx) == "us-east"
        assert baggage.get_baggage("invalid", ctx) is None

    def test_roundtrip(self):
        propagator = BaggagePropagator()

        # Set original baggage
        ctx = baggage.set_baggage("userId", "alice")
        ctx = baggage.set_baggage("data", "a=b&c=d", context=ctx)

        # Inject
        carrier = {}
        propagator.inject(carrier, context=ctx)

        # Extract
        extracted_ctx = propagator.extract(carrier)

        # Verify
        assert baggage.get_baggage("userId", extracted_ctx) == "alice"
        assert baggage.get_baggage("data", extracted_ctx) == "a=b&c=d"


class TestCompositePropagator:
    def test_fields_combines_all(self):
        propagator = CompositePropagator([
            TraceContextPropagator(),
            BaggagePropagator(),
        ])

        fields = propagator.fields
        assert "traceparent" in fields
        assert "tracestate" in fields
        assert "baggage" in fields

    def test_inject_calls_all_propagators(self):
        propagator = CompositePropagator([
            TraceContextPropagator(),
            BaggagePropagator(),
        ])
        carrier = {}

        # Set up context with span and baggage
        sc = SpanContext(
            trace_id=0x4BF92F3577B34DA6A3CE929D0E0E4736,
            span_id=0x00F067AA0BA902B7,
            is_remote=False,
            trace_flags=TraceFlags.SAMPLED,
        )
        span = NonRecordingSpan(sc)
        ctx = trace.set_span_in_context(span)
        ctx = baggage.set_baggage("userId", "alice", context=ctx)

        propagator.inject(carrier, context=ctx)

        assert TRACEPARENT_HEADER in carrier
        assert BAGGAGE_HEADER in carrier
        assert carrier[BAGGAGE_HEADER] == "userId=alice"

    def test_extract_calls_all_propagators(self):
        propagator = CompositePropagator([
            TraceContextPropagator(),
            BaggagePropagator(),
        ])
        carrier = {
            TRACEPARENT_HEADER: "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            BAGGAGE_HEADER: "userId=alice",
        }

        ctx = propagator.extract(carrier)

        # Check trace context
        span = trace.get_current_span(ctx)
        sc = span.get_span_context()
        assert sc.is_valid
        assert sc.trace_id == 0x4BF92F3577B34DA6A3CE929D0E0E4736

        # Check baggage
        assert baggage.get_baggage("userId", ctx) == "alice"


class TestGetDefaultPropagator:
    def test_returns_composite_with_tracecontext_and_baggage(self):
        propagator = get_default_propagator()

        assert isinstance(propagator, CompositePropagator)
        assert "traceparent" in propagator.fields
        assert "baggage" in propagator.fields
