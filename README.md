# otelmini

A minimal OpenTelemetry Python SDK with only `opentelemetry-api` as a dependency. Exports traces, metrics, and logs via JSON-OTLP over HTTP. Ideal for constrained environments like AWS Lambda or anywhere minimal production impact is valued.

## Features

- Traces, metrics, and logs support
- JSON-OTLP over HTTP (no protobuf, no gRPC)
- Single dependency: `opentelemetry-api`
- Batch processing with configurable size and interval
- Auto-instrumentation support

## Installation

```bash
pip install otelmini
```

## Quick Start

```python
import os
from opentelemetry import trace
from otelmini.processor import BatchProcessor
from otelmini.trace import HttpSpanExporter, MiniTracerProvider

os.environ["OTEL_SERVICE_NAME"] = "my-service"

tp = MiniTracerProvider(BatchProcessor(HttpSpanExporter()))
trace.set_tracer_provider(tp)
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("my-operation"):
    # your code here
    pass

tp.shutdown()
```

## Auto-Instrumentation

Use the `otel` command to automatically instrument any application that uses the OpenTelemetry API:

```bash
otel python my_app.py
```

This works with any code already instrumented via `opentelemetry-api`—no code changes required.

## Why otelmini?

The standard OpenTelemetry Python exporters require protobuf at minimum. otelmini uses JSON-OTLP over HTTP, avoiding protobuf and gRPC entirely while remaining OTLP-compliant.

This is useful when:

- **Avoiding dependency conflicts** — your project requires a different version of protobuf, requests, or gRPC than OTel exporters expect
- **Minimizing package size** — serverless environments like AWS Lambda have size limits
- **Reducing attack surface** — fewer dependencies means less to audit and maintain
