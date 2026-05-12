from opentelemetry import trace
from opentelemetry.trace import Link, NonRecordingSpan, TraceFlags
from opentelemetry.trace.span import TraceState

from otelmini.export import Retrier, RetrierResult
from otelmini.processor import BatchProcessor
from otelmini.sampler import AlwaysOffSampler
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


class RecordingSpanProcessor:
    def __init__(self):
        self.started = []
        self.ended = []

    def on_start(self, span):
        self.started.append(span)

    def on_end(self, span):
        self.ended.append(span)

    def force_flush(self, timeout_millis=30_000):
        return True

    def shutdown(self):
        pass


def test_span_is_recording_until_ended():
    span = MiniSpan(
        name="test-span",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None
    )

    assert span.is_recording()
    span.set_status("ERROR")
    assert span.is_recording()
    span.end()
    assert not span.is_recording()


def test_span_end_is_idempotent():
    ended_spans = []
    span = MiniSpan(
        name="test-span",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=ended_spans.append,
    )

    span.end(100)
    span.end(200)

    assert span.get_end_time() == 100
    assert ended_spans == [span]


def test_span_mutations_after_end_are_ignored():
    span = MiniSpan(
        name="original",
        span_context=SpanContext(trace_id=1, span_id=2, is_remote=False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda s: None,
        attributes={"existing": "value"},
    )
    span.add_event("before-end", {"kept": True}, 100)
    span.set_status("ERROR", "before end")
    span.end()

    span.set_attribute("late", "ignored")
    span.set_attributes({"also": "ignored"})
    span.add_event("after-end", {"ignored": True}, 200)
    span.record_exception(ValueError("ignored"), {"ignored": True}, 300)
    span.update_name("renamed")
    span.set_status("OK", "after end")

    assert span.get_name() == "original"
    assert span.get_attributes() == {"existing": "value"}
    assert span.get_events() == [("before-end", {"kept": True}, 100)]
    assert span.get_status() == "ERROR"
    assert span.get_status_description() == "before end"


def test_start_span_honors_start_time():
    provider = MiniTracerProvider(span_processor=RecordingSpanProcessor())
    tracer = provider.get_tracer("test")

    span = tracer.start_span("span", start_time=12345)

    assert span.get_start_time() == 12345


def test_start_as_current_span_honors_end_on_exit_false():
    processor = RecordingSpanProcessor()
    provider = MiniTracerProvider(span_processor=processor)
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("span", end_on_exit=False) as span:
        assert trace.get_current_span() is span

    assert span.get_end_time() is None
    assert processor.ended == []

    span.end(123)
    assert span.get_end_time() == 123
    assert processor.ended == [span]


def test_dropped_span_returns_non_recording_span_with_valid_context():
    processor = RecordingSpanProcessor()
    provider = MiniTracerProvider(
        span_processor=processor, sampler=AlwaysOffSampler()
    )
    tracer = provider.get_tracer("test")

    span = tracer.start_span("dropped")
    span_context = span.get_span_context()

    assert isinstance(span, NonRecordingSpan)
    assert span_context.is_valid
    assert span_context.trace_id != 0
    assert span_context.span_id != 0
    assert not span.is_recording()
    assert not span_context.trace_flags & TraceFlags.SAMPLED
    assert processor.started == []
    assert processor.ended == []

    span.end()
    assert processor.ended == []


def test_dropped_child_span_preserves_parent_trace_id():
    provider = MiniTracerProvider(sampler=AlwaysOffSampler())
    tracer = provider.get_tracer("test")
    parent = tracer.start_span("parent")

    child = tracer.start_span(
        "child",
        context=trace.set_span_in_context(parent),
    )

    parent_context = parent.get_span_context()
    child_context = child.get_span_context()

    assert isinstance(child, NonRecordingSpan)
    assert child_context.is_valid
    assert child_context.trace_id == parent_context.trace_id
    assert child_context.span_id != parent_context.span_id
    assert not child_context.trace_flags & TraceFlags.SAMPLED


def test_dropped_span_inherits_parent_trace_state():
    trace_state = TraceState([("vendor", "value")])
    parent_context = SpanContext(
        trace_id=0x1234567890ABCDEF1234567890ABCDEF,
        span_id=0x1234567890ABCDEF,
        is_remote=True,
        trace_flags=TraceFlags.DEFAULT,
        trace_state=trace_state,
    )
    parent = NonRecordingSpan(parent_context)
    provider = MiniTracerProvider(sampler=AlwaysOffSampler())
    tracer = provider.get_tracer("test")

    span = tracer.start_span(
        "child",
        context=trace.set_span_in_context(parent),
    )
    span_context = span.get_span_context()

    assert isinstance(span, NonRecordingSpan)
    assert span_context.trace_state.get("vendor") == "value"
    assert not span_context.is_remote
