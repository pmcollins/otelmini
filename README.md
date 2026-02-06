# otelmini

A minimal OpenTelemetry Python SDK with no extra dependencies. Exports traces, metrics, and logs via OTLP/HTTP (JSON
encoding). Ideal for constrained environments like AWS Lambda or anywhere minimal production impact is valued.

## Features

- Traces, metrics, and logs support
- OTLP/HTTP with JSON encoding
- Single dependency: `opentelemetry-api`
- Batch processing with configurable size and interval
- Auto-instrumentation support
- W3C TraceContext and Baggage propagation

## Installation

```bash
pip install otelmini
```

## Quick Start

Write your application using the OpenTelemetry API:

```python
# my_app.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("my-operation"):
    # your code here
    pass
```

Run it with otelmini's auto-instrumentation using the installed `otel` command:

```bash
OTEL_SERVICE_NAME=my-service otel python my_app.py
```

That's it -- traces are exported to `localhost:4318` via OTLP/HTTP (JSON).

## Why otelmini?

otelmini was designed with minimalism as a goal, giving you insight into your applications via any of the
[standard](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation)
or [genai](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation-genai)
instrumentation libraries while staying out of the way. No dependencies other than opentelemetry-api, which you have to
use anyway if you're using OTel at all.

This is useful when:

- **Avoiding dependency conflicts** -- your project requires a different version of protobuf or requests than OTel exporters expect
- **Minimizing package size** -- serverless environments like AWS Lambda have size limits
- **Reducing cold start time** -- fewer modules to load means faster Lambda cold starts
- **Reducing attack surface** -- fewer dependencies means less to audit and maintain
- **Improving performance** -- less code means potentially lower memory impact and faster execution

## Comparison with OpenTelemetry Python

Comparing `otelmini` to `opentelemetry-distro` + `opentelemetry-exporter-otlp-proto-http`:

| Metric                    | otel-python | otelmini |
|---------------------------|-------------|----------|
| Third-party dependencies* | 9           | 0        |
| Lines of Python           | 43K         | 2K       |
| Fun                       | 🙂          | 😁       |

\* Excluding opentelemetry packages and Python stdlib backports

Note: Upstream otel-python doesn't support JSON/HTTP -- their OTLP exporters require protobuf.

<details>
<summary>Third-party packages installed by otel-python</summary>

- protobuf, googleapis-common-protos
- requests, urllib3, certifi, charset-normalizer, idna
- wrapt, packaging

</details>

## Spec Conformance

See [SPEC_CONFORMANCE.md](SPEC_CONFORMANCE.md) for details on OpenTelemetry specification compliance.

## License

Apache-2.0
