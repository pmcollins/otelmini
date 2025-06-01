from otelmini._lib import Retrier, RetrierResult
from otelmini.trace import MiniSpan, Resource, InstrumentationScope, SpanContext
from tests._lib import StubbornRunner, FakeSleeper


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
