from opentelemetry.trace import SpanContext

from otelmini._tracelib import InstrumentationScope, MiniSpan, Resource


def mk_span(name):
    return MiniSpan(
        name,
        span_context=SpanContext(0, 0, False),
        resource=Resource(""),
        instrumentation_scope=InstrumentationScope("", "")
    )
