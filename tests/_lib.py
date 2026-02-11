from opentelemetry.trace import SpanContext

from otelmini.export import SingleAttemptResult
from otelmini.trace import InstrumentationScope, MiniSpan, Resource


def mk_span(name):
    return MiniSpan(
        name,
        span_context=SpanContext(0, 0, False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        on_end_callback=lambda _: None
    )


class FakeSleeper:

    def __init__(self):
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)


class StubbornRunner:
    """For testing Retrier"""

    def __init__(self, num_failures_before_success, func):
        self.i = 0
        self.num_failures_before_success = num_failures_before_success
        self.func = func

    def attempt(self):
        self.i += 1
        if self.i <= self.num_failures_before_success:
            return SingleAttemptResult.RETRY
        else:
            self.func()
            return SingleAttemptResult.SUCCESS


class RecordingExporter:
    """Exporter that records all exported items for testing."""

    def __init__(self):
        self.items = []

    def export(self, items):
        self.items.extend(items)
        return SingleAttemptResult.SUCCESS
