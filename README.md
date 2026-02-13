# otelmini

A minimal OpenTelemetry Python SDK with no extra dependencies. Exports traces, metrics, and logs via OTLP/HTTP (JSON
encoding). Ideal for constrained environments like AWS Lambda or anywhere minimal production impact is valued.

## Features

- Traces, metrics, and logs support
- OTLP/HTTP with JSON encoding
- Single dependency: `opentelemetry-api`
- Batch processing with configurable size and interval
- Sampling (AlwaysOn, AlwaysOff, TraceIdRatioBased, ParentBased)
- Trace-log correlation
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

### Using Instrumentation Libraries

otelmini works with OpenTelemetry instrumentation libraries from [opentelemetry-python-contrib](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation) or any other code that uses the OpenTelemetry API. For example, to automatically instrument HTTP calls made with the `requests` library:

```bash
pip install otelmini opentelemetry-instrumentation-requests
```

Then run your application using the `otel` command, which handles auto-instrumentation:

```bash
OTEL_SERVICE_NAME=my-service otel python my_app.py
```

The `otel` command automatically discovers and activates any installed instrumentation libraries at startup. All HTTP requests made via the `requests` library will now be traced with spans containing HTTP method, URL, status code, and timing information.

This pattern works with any instrumentation library from the contrib repository, including the [genai instrumentation libraries](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation-genai) for observing LLM applications.

**Note:** You can also wire up instrumentation manually using the otelmini SDK directly and calling the instrumentor's `instrument()` method yourself, but the `otel` command automatically sets up the SDK and handles instrumentation discovery and activation for you.

## Why otelmini?

otelmini was designed with minimalism as a goal, giving you insight into your applications via OpenTelemetry instrumentation libraries while staying out of the way. No dependencies other than opentelemetry-api, which you have to use anyway if you're using OTel at all.

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
| Lines of Python           | ~47K        | ~3.1K    |

\* Excluding opentelemetry packages and Python stdlib backports

Note: Upstream otel-python doesn't support JSON/HTTP -- their OTLP exporters require protobuf.

### AWS Lambda Performance

Tested using SAM CLI with Python 3.11 runtime:

| Metric            | otel-python | otelmini | Improvement      |
|-------------------|-------------|----------|------------------|
| Package size      | 7.0 MB      | 824 KB   | **8.5x smaller** |
| Cold start (init) | ~256 ms     | ~80 ms   | **3x faster**    |
| Import time       | ~287 ms     | ~108 ms  | **2.7x faster**  |

See `tests/oteltest/lambda-comparison/` to run the benchmark yourself.

<details>
<summary>Third-party packages installed by otel-python</summary>

- protobuf, googleapis-common-protos
- requests, urllib3, certifi, charset-normalizer, idna
- wrapt, packaging

</details>

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_SERVICE_NAME` | Service name for resource | `unknown_service` |
| `OTEL_RESOURCE_ATTRIBUTES` | Additional resource attributes (`key=value,key2=value2`) | |
| `OTEL_TRACES_EXPORTER` | Traces exporter (`otlp`, `console`, `none`) | `otlp` |
| `OTEL_METRICS_EXPORTER` | Metrics exporter (`otlp`, `console`, `none`) | `otlp` |
| `OTEL_LOGS_EXPORTER` | Logs exporter (`otlp`, `console`, `none`) | `otlp` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Base OTLP endpoint | `http://localhost:4318` |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Traces endpoint (overrides base) | |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Metrics endpoint (overrides base) | |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | Logs endpoint (overrides base) | |
| `OTEL_BSP_MAX_EXPORT_BATCH_SIZE` | Batch processor max batch size | `512` |
| `OTEL_BSP_SCHEDULE_DELAY` | Batch processor schedule delay (ms) | `5000` |
| `OTEL_METRIC_EXPORT_INTERVAL` | Metric export interval (ms) | `10000` |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | Semantic conventions to use (comma-separated) | `http,database` |

otelmini defaults to stable (new) semantic conventions. Valid values: `http`, `http/dup`, `database`, `database/dup`, `gen_ai_latest_experimental`. Set to `http/dup,database/dup` to emit both old and new attributes, or set to empty string to use old conventions only.

Third-party exporters can be installed and will be discovered via entry points. Use `otlp_json_http` for explicit JSON/HTTP selection.

## Custom Exporters

To create a custom exporter, implement the `Exporter` interface and register via entry points.

### Interface

```python
from otelmini.export import Exporter, ExportResult

class MySpanExporter(Exporter):
    def __init__(self, **kwargs):
        # Accept endpoint and other kwargs
        self.endpoint = kwargs.get("endpoint")

    def export(self, items):
        # items is Sequence[MiniSpan] for traces
        # Return ExportResult.SUCCESS or ExportResult.FAILURE
        return ExportResult.SUCCESS
```

Data types passed to `export()`:
- **Traces**: `Sequence[MiniSpan]` from `otelmini.types`
- **Metrics**: `MetricsData` from `otelmini.point`
- **Logs**: `Sequence[MiniLogRecord]` from `otelmini.log`

### Registration

In your package's `pyproject.toml`:

```toml
[project.entry-points.opentelemetry_traces_exporter]
my_exporter = "my_package:MySpanExporter"

[project.entry-points.opentelemetry_metrics_exporter]
my_exporter = "my_package:MyMetricExporter"

[project.entry-points.opentelemetry_logs_exporter]
my_exporter = "my_package:MyLogExporter"
```

Then users can select it via environment variable:

```bash
OTEL_TRACES_EXPORTER=my_exporter otel python app.py
```

## Spec Compliance

See [SPEC_COMPLIANCE.md](SPEC_COMPLIANCE.md) for details on OpenTelemetry specification compliance.

## License

Apache-2.0
