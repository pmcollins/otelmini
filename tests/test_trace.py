from opentelemetry.trace import Link

from otelmini.export import Retrier, RetrierResult
from otelmini.processor import BatchProcessor
from otelmini.trace import MiniSpan, MiniTracerProvider, Resource, InstrumentationScope, SpanContext
from otelmini.encode import _encode_span, _encode_event
from tests._lib import StubbornRunner, FakeSleeper, RecordingExporter


def test_retrier_eventual_success():
    greeter = StubbornRunner(2, lambda: "hello")
    f = FakeSleeper()
    backoff = Retrier(max_retries=2, sleep=f.sleep)
    assert backoff.retry(lambda: greeter.attempt()) == RetrierResult.SUCCESS
    assert f.sleeps == [1, 2]


def test_span_dict_serialization():
    span = MiniSpan(
        name="test",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None
    )

    span_dict = span.to_dict()
    new_span = MiniSpan.from_dict(span_dict, on_end_callback=lambda s: None)

    assert new_span.get_name() == "test"
    assert new_span.get_span_context().trace_id == 1
    assert new_span.get_span_context().span_id == 2


def test_encode_event_with_all_fields():
    event = ("test-event", {"key": "value"}, 1234567890)
    encoded = _encode_event(event)
    assert encoded["name"] == "test-event"
    assert encoded["timeUnixNano"] == "1234567890"
    assert encoded["attributes"] == [{"key": "key", "value": {"stringValue": "value"}}]


def test_encode_event_without_timestamp():
    # When timestamp is None in the tuple, no timeUnixNano is encoded
    # (But add_event now auto-generates timestamps, so this tests the encoder edge case)
    event = ("test-event", {"key": "value"}, None)
    encoded = _encode_event(event)
    assert encoded["name"] == "test-event"
    assert "timeUnixNano" not in encoded
    assert "attributes" in encoded


def test_add_event_auto_generates_timestamp():
    from otelmini.trace import MiniSpan, Resource, InstrumentationScope, SpanContext
    span = MiniSpan(
        name="test-span",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None
    )
    span.add_event("auto-timestamp-event", {"key": "value"})
    events = span.get_events()
    assert len(events) == 1
    name, attrs, timestamp = events[0]
    assert name == "auto-timestamp-event"
    assert timestamp is not None
    assert timestamp > 0


def test_encode_event_without_attributes():
    event = ("test-event", None, 1234567890)
    encoded = _encode_event(event)
    assert encoded["name"] == "test-event"
    assert encoded["timeUnixNano"] == "1234567890"
    assert "attributes" not in encoded


def test_encode_span_with_events():
    span = MiniSpan(
        name="test-span",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None
    )
    span.add_event("event1", {"attr1": "val1"}, 1000)
    span.add_event("event2", {"attr2": 42}, 2000)
    span.end()

    encoded = _encode_span(span)
    assert "events" in encoded
    assert len(encoded["events"]) == 2
    assert encoded["events"][0]["name"] == "event1"
    assert encoded["events"][0]["timeUnixNano"] == "1000"
    assert encoded["events"][1]["name"] == "event2"
    assert encoded["events"][1]["attributes"] == [{"key": "attr2", "value": {"intValue": "42"}}]


def test_encode_span_without_events():
    span = MiniSpan(
        name="test-span",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None
    )
    span.end()

    encoded = _encode_span(span)
    assert "events" not in encoded


def test_span_with_links():
    linked_ctx = SpanContext(trace_id=0xABCDEF, span_id=0x123456, is_remote=True)
    link = Link(context=linked_ctx, attributes={"link.type": "parent"})

    span = MiniSpan(
        name="test-span",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None,
        links=[link],
    )

    assert len(span.get_links()) == 1
    assert span.get_links()[0].context.trace_id == 0xABCDEF


def test_encode_span_with_links():
    linked_ctx = SpanContext(trace_id=0xABCDEF123456, span_id=0x789ABC, is_remote=True)
    link = Link(context=linked_ctx, attributes={"reason": "follows-from"})

    span = MiniSpan(
        name="test-span",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None,
        links=[link],
    )
    span.end()

    encoded = _encode_span(span)
    assert "links" in encoded
    assert len(encoded["links"]) == 1
    assert encoded["links"][0]["traceId"] == "00000000000000000000abcdef123456"
    assert encoded["links"][0]["spanId"] == "0000000000789abc"
    assert encoded["links"][0]["attributes"] == [{"key": "reason", "value": {"stringValue": "follows-from"}}]


def test_encode_span_without_links():
    span = MiniSpan(
        name="test-span",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None
    )
    span.end()

    encoded = _encode_span(span)
    assert "links" not in encoded


def test_tracer_provider_force_flush():
    exporter = RecordingExporter()
    processor = BatchProcessor(exporter, batch_size=100, interval_seconds=60)
    provider = MiniTracerProvider(span_processor=processor)
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("span1"):
        pass
    with tracer.start_as_current_span("span2"):
        pass

    # Spans are batched, not yet exported
    assert len(exporter.items) == 0

    # force_flush exports immediately
    result = provider.force_flush()
    assert result is True
    assert len(exporter.items) == 2
    assert exporter.items[0].get_name() == "span1"
    assert exporter.items[1].get_name() == "span2"

    provider.shutdown()


def test_tracer_provider_force_flush_no_processor():
    provider = MiniTracerProvider()
    # Should return True when no processor is configured
    assert provider.force_flush() is True
