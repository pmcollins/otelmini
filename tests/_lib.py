from opentelemetry.trace import SpanContext

from otelmini.trace import InstrumentationScope, MiniSpan, Resource, SpanProcessor


class FakeSpanProcessor(SpanProcessor):

    def on_start(self, span: MiniSpan) -> None:
        pass

    def on_end(self, span) -> None:
        pass


def mk_span(name):
    return MiniSpan(
        name,
        span_context=SpanContext(0, 0, False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", ""),
        span_processor=FakeSpanProcessor(),
    )
