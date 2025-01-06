from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanContext


def mk_span(name):
    return ReadableSpan(name, context=SpanContext(0, 0, False))
