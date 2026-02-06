# otelmini

A minimal OpenTelemetry Python SDK with only `opentelemetry-api` as a dependency. Exports traces, metrics, and logs via JSON-OTLP over HTTP. Ideal for constrained environments like AWS Lambda or anywhere minimal production impact is valued.

## Features

- Traces, metrics, and logs support
- JSON-OTLP over HTTP (no protobuf, no gRPC)
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

Run it with otelmini's auto-instrumentation:

```bash
OTEL_SERVICE_NAME=my-service otel python my_app.py
```

That's it—traces are exported to `localhost:4318` via OTLP/HTTP.

## Why otelmini?

The standard OpenTelemetry Python exporters require protobuf at minimum. otelmini uses JSON-OTLP over HTTP, avoiding protobuf and gRPC entirely while remaining OTLP-compliant.

This is useful when:

- **Avoiding dependency conflicts** — your project requires a different version of protobuf, requests, or gRPC than OTel exporters expect
- **Minimizing package size** — serverless environments like AWS Lambda have size limits
- **Reducing cold start time** — fewer modules to load means faster Lambda cold starts
- **Reducing attack surface** — fewer dependencies means less to audit and maintain

## Comparison with OpenTelemetry Python

Comparing `otelmini` to `opentelemetry-distro` + `opentelemetry-exporter-otlp-proto-http`:

| Metric | otelmini | otel-python | Reduction |
|--------|----------|-------------|-----------|
| Third-party dependencies* | 0 | 9 | 100% fewer |
| Install size | 9.7 MB | 17 MB | 43% smaller |
| Lines of Python | 2K | 43K | 95% fewer |

\* Excluding opentelemetry packages and Python stdlib backports

Note: Upstream otel-python doesn't support JSON/HTTP—their OTLP exporters require protobuf.

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
