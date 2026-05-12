# OpenTelemetry Specification Compliance Audit

Audit date: 2026-05-12

SDK under review: current `otelmini` worktree in `/Users/pabcolli/github/pmcollins/otelmini`.

Specification source: local checkout at `/Users/pabcolli/github/open-telemetry/opentelemetry-specification`, revision `v1.56.0-23-g15f8864` (`15f8864`), clean at audit time.

This audit treats the current worktree as the implementation under review, including the pending metric instrument registry changes in `src/otelmini/metric.py`.

## Scope

Reviewed implementation paths:

- `src/otelmini/trace.py`, `sampler.py`, `types.py`
- `src/otelmini/metric.py`, `point.py`
- `src/otelmini/log.py`
- `src/otelmini/processor.py`, `export.py`, `encode.py`
- `src/otelmini/resource.py`, `propagator.py`, `env.py`
- `src/otelmini/auto/_lib.py`, `distro.py`
- Unit and scenario tests under `tests/`

Reviewed specification sections:

- `specification/trace/api.md`, `trace/sdk.md`, `trace/exceptions.md`
- `specification/metrics/api.md`, `metrics/sdk.md`, `metrics/data-model.md`
- `specification/logs/api.md`, `logs/sdk.md`, `logs/data-model.md`
- `specification/resource/sdk.md`, `resource/data-model.md`
- `specification/context/api-propagators.md`, `baggage/api.md`
- `specification/configuration/sdk-environment-variables.md`
- `specification/protocol/exporter.md`, `protocol/otlp.md`
- `specification/error-handling.md`

Not covered in depth: profiles, schemas, semantic-convention coverage beyond resource defaults, OpenCensus/OpenTracing compatibility, Prometheus/Zipkin exporters, and the configuration file data model.

## Status Key

- **Compliant**: meets the reviewed requirement in observable SDK/export behavior.
- **Partial**: implements a useful subset, but drops required fields, misses lifecycle semantics, or omits required variants.
- **Gap**: required behavior is missing or materially incorrect.
- **Not applicable**: outside the current implementation scope.

## Executive Summary

`otelmini` is a compact SDK-like implementation that covers the happy path for spans, several metric instruments, basic logs, resources, W3C traceparent extraction/injection, baggage, batching, and OTLP/JSON export. It is not currently a conforming OpenTelemetry SDK. The largest gaps are not just missing optional features; several required API/SDK semantics are incorrect in exported behavior.

The previous report overstated compliance. In several places the SDK accepts a spec parameter but ignores it, stores data internally but fails to encode it, or exposes methods with names similar to the spec but not the required lifecycle semantics.

| Area | Current conformance | Strong points | Largest blockers |
| --- | --- | --- | --- |
| Traces | Partial | Basic span creation/export, resources, scope grouping, parent trace ID, span links at creation | Dropped spans return `INVALID_SPAN`; span lifecycle and `is_recording()` are wrong; `start_time` ignored; status and exception conventions not exported; no post-creation `AddLink`; sampler contract incomplete |
| Metrics | Partial | Core sync/async instruments exist; cumulative Sum/Gauge/ExplicitBucketHistogram data is produced; identical sync instruments now share state for simple cases | No Views; no reader-specific aggregation/temporality; async callbacks only use first observation and drop attributes; histogram boundary placement is wrong; incomplete instrument identity; readers/exporters do not satisfy lifecycle semantics |
| Logs | Low partial | LoggerProvider and stdlib bridge exist; resource attached; basic severity/body/attributes captured | Export omits trace context, observed timestamp, event name, and instrumentation scope; `context` and `event_name` args ignored; no exception handling; no LoggerConfig/filtering/Enabled; no proper `OnEmit` processor model |
| Resource | Partial | Resource creation, merge, SDK attrs, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_SERVICE_NAME` precedence | Resource is mutable; env parsing lacks percent decoding and error reporting; default resource/detector support incomplete |
| Propagation and baggage | Partial | W3C `traceparent` and basic baggage supported; malformed `traceparent` preserves context | No `tracestate` parse/inject; no full W3C baggage validation/metadata preservation; no `OTEL_PROPAGATORS` configuration |
| Configuration/export | Partial | Some env vars implemented; signal-specific OTLP endpoints; console/OTLP exporter selection | Many required/standard env vars missing; OTLP default transport is JSON not protobuf; no headers/compression/TLS handling; retry lacks jitter; timeouts/lifecycle incomplete |
| Error handling/concurrency | Partial | Many exporter, processor, and callback exceptions are caught and logged | Several API calls can still throw on invalid attribute values; no custom error handler; most API/SDK objects are not documented or implemented as thread-safe |

## Highest-Impact Findings

1. **Trace sampling and span lifecycle are not spec compliant.** The SDK returns `INVALID_SPAN` for `DROP`, which loses the valid trace context that the spec requires a non-recording span to carry. `MiniSpan.is_recording()` depends on status rather than end state, repeated `end()` calls export repeatedly, and mutations after end still change the span.

2. **Trace exported data is missing required semantics.** Span status is never encoded, `record_exception()` creates an event named after the exception class instead of `"exception"` with `exception.*` attributes, start timestamps passed to `start_span()` are ignored, and post-creation `AddLink` is absent.

3. **Metrics needs Views and real reader semantics before it can be considered SDK compliant.** The spec requires View registration, reader-specific aggregation/temporality/cardinality behavior, and `Collect`/`ForceFlush`/`Shutdown` semantics. The current readers mostly use `force_flush()` as collection and do not propagate exporter failures or exporter shutdown.

4. **Asynchronous metrics are materially incomplete.** Async callbacks must be evaluated for the specific `MetricReader`, and observations can carry attributes and multiple values. Current observable instruments return only the first observation value, drop observation attributes, and emit `0.0` if no callback succeeds.

5. **Logs are captured but not exported with the data model required by the spec.** The log object may store trace IDs and observed timestamps, but `_encode_log_record()` omits `traceId`, `spanId`, `flags`, `observedTimeUnixNano`, `eventName`, and scope information.

6. **OTLP exporter behavior is partial.** The exporter sends OTLP/JSON over plain `HTTPConnection`; the spec defaults to `http/protobuf`, requires signal-specific endpoint behavior, headers, compression, timeouts, transient retry with jitter, and HTTPS support when configured.

## Traces

### API and Provider

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| `TracerProvider.get_tracer(name, version, schema_url, attributes)` accepts full instrumentation scope | `MiniTracerProvider.get_tracer()` accepts all args, but constructs `InstrumentationScope(name, version)` only | Partial | `schema_url` and scope `attributes` are dropped before export. Invalid names return a tracer, but no invalid-name warning is logged. |
| Already returned tracers see provider config updates | No dynamic provider configuration model | Gap | This matters for processors/configurator behavior described in Trace SDK. |
| `Tracer.Enabled` API | Not implemented | Gap | Required as a SHOULD in API and tied to SDK config in development sections. |
| Span creation accepts context, kind, attributes, links, start timestamp | Mostly accepted | Partial | `context`, `kind`, `attributes`, and creation `links` work. `start_time` is not passed to `MiniSpan`, so it is ignored. |
| `start_as_current_span()` honors `record_exception`, `set_status_on_exception`, and `end_on_exit` | Parameters are accepted but mishandled | Gap | Positional call passes `end_on_exit` into `record_exception`, ignores `set_status_on_exception`, and always calls `trace.use_span(..., end_on_exit=True)`. |
| Child span trace ID matches parent and inherits parent `TraceState` | Trace ID and parent span ID are preserved | Partial | New `SpanContext` does not carry parent `trace_state`, so TraceState inheritance is missing. |
| Root span creation option and new trace ID per root span | New trace ID generated when current/explicit context has no valid span | Partial | Explicit root creation depends on passing an empty context through upstream API patterns; no dedicated API behavior is documented locally. |

### Span Behavior

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| `get_span_context()` returns stable context | Implemented | Compliant | Uses upstream `SpanContext`. |
| `is_recording()` true while recording and false after end | `return self._status is None` | Gap | Setting status makes an active span non-recording; ending a span with no status leaves it recording. |
| After `End`, subsequent span methods should be ignored | Mutations after `end()` still apply | Gap | `end()` can be called repeatedly and each call invokes the processor again. |
| `End` should not perform blocking I/O on caller thread | Batch processor enqueue is non-I/O | Partial | The default batch path is non-I/O, but custom processors are called synchronously and there is no processor interface contract/timeout. |
| Set attributes and add events | Implemented | Partial | Basic storage works, but no span limits, dropped counts, or post-end guard. |
| Add links after creation | No `add_link()` implementation | Gap | Creation-time links are supported and encoded. |
| Set status with spec semantics | Stored but not exported | Gap | `_encode_span()` always emits `"status": {}`. No status precedence, no `OK` finality, no description restrictions. |
| Record exception event | Adds event named exception class | Gap | Spec requires an event named `"exception"` with exception semantic attributes such as type, message, and stacktrace. |
| Thread-safe API methods | No locking around span mutation | Gap | Span events, links, attrs, status, and end state are mutable without synchronization. |

### Sampling and IDs

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| Default sampler is ParentBased(root=AlwaysOn) | Provider defaults to `AlwaysOnSampler()` | Gap | Unsampled parents can produce sampled children by default. |
| Span creation order: generate trace ID, call sampler, generate span ID independent of decision, create span according to decision | Span ID generated only after sample decision | Gap | `DROP` returns `INVALID_SPAN`, not a valid non-recording span context. |
| `DROP`, `RECORD_ONLY`, `RECORD_AND_SAMPLE` decisions | Only `DROP` and `RECORD_AND_SAMPLE` exist | Gap | No `RECORD_ONLY`; no sampled flag distinction for record-only spans. |
| `ShouldSample` receives context, trace ID, name, span kind, attributes, links | Sampler receives trace ID, name, optional parent context | Gap | Samplers cannot inspect kind, attributes, links, or full context. |
| Sampling result can add attributes and return TraceState | `SamplingResult` only has `decision` | Gap | No sampling attributes and no TraceState updates. |
| `GetDescription()` on samplers | Not implemented | Gap | Required by sampler interface/concurrency requirements. |
| Trace ID and span ID generation are non-zero and customizable | Uses `random.getrandbits()` directly | Partial | IDs are random, but zero is theoretically possible and no `IdGenerator` extension exists. |
| Ratio sampler deterministic hash behavior | Uses low 64 bits comparison | Partial | Deterministic for a trace ID, but not the spec's current hash/randomness requirements. |

### Processors and Exporters

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| SDK allows custom processors and pipelines | Provider accepts one `span_processor` | Partial | No list/multi-processor pipeline and no add-processor API. |
| SpanProcessor interface declares `OnStart`, `OnEnd`, `Shutdown`, `ForceFlush` | Generic `Processor` only declares `on_start` and `on_end` | Partial | `BatchProcessor` has `shutdown()`/`force_flush()`, but the interface does not require them. |
| Standard SDK implements simple and batch processors | Only `BatchProcessor` exists | Gap | No SimpleSpanProcessor. |
| BatchSpanProcessor queue, batch size, delay, export timeout defaults and constraints | Batch size and delay exist | Partial | No max queue size/drop behavior, no export timeout enforcement, no validation that batch size <= queue size, no dropped counts. |
| Processor/exporter `ForceFlush` and `Shutdown` include exporter lifecycle | `BatchProcessor.force_flush()` exports current batches only; `shutdown()` stops timer | Partial | Does not call exporter `force_flush()`/`shutdown()`, does not join the worker thread, and does not report exporter failure. |
| Export calls are synchronized | Batcher has locks, exporter call synchronization is not explicit | Partial | Force flush and timer stop can both call export paths; no exporter-level serialization contract. |
| SpanExporter supports Export, ForceFlush, Shutdown | Base methods exist | Partial | Exporters have no shutdown state and export after shutdown is not guarded. |

## Metrics

### API and Provider

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| `MeterProvider.get_meter(name, version, schema_url, attributes)` creates instrumentation scope | Method accepts args, returns `Meter(self, name, version, schema_url)` | Partial | Scope attributes are ignored. `MetricProducer` groups only by meter name and emits `InstrumentationScope(name=meter_name)` with no version, schema URL, or attributes. |
| Invalid meter names return working meter and log | No validation/rejection | Partial | Working meter is returned, but no invalid-name diagnostic. |
| Provider owns metric readers/exporters/views and applies updates to existing meters | Static constructor list only | Partial | Readers are set at construction; no add/update configuration model. |
| `Meter.Enabled` / MeterConfig | Not implemented | Gap | No enabled config or disabled no-op behavior. |
| Views can be created and registered with `MeterProvider` | No View implementation | Gap | This is a central Metrics SDK requirement. |

### Instruments

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| Counter, UpDownCounter, Histogram, Gauge | Implemented | Partial | Basic methods work. No instrument `Enabled()`, validation diagnostics, attribute limits, or thread-safe aggregation state. |
| ObservableCounter, ObservableUpDownCounter, ObservableGauge | Implemented | Partial | Callback support is a small subset; see async section below. |
| Identical instruments aggregate into one stream | Provider registry keys by `(meter_name, instrument_type, name, unit, description)` | Partial | Fixes duplicate data points for simple same-meter cases. It does not include full instrumentation scope, does not normalize case-insensitive instrument names, and second creation of an identical observable instrument drops additional callbacks. |
| Instrument names are case-insensitive ASCII with max length 255 | No validation/normalization | Gap | `requests` and `Requests` are treated as different instruments. |
| Synchronous Counter rejects negative values without disrupting app | Logs and ignores negative monotonic counter values | Partial | Safe behavior, but no SDK-level error handling customization. |
| Histogram default explicit boundaries | Uses spec default boundaries | Partial | Boundary assignment uses `amount < bound`; spec buckets are inclusive upper-bound, so exact boundary values go into the wrong bucket. |
| Histogram advisory explicit boundaries | Constructor accepts advisory boundaries | Partial | No View precedence exists, and canonical instrument reuse ignores later advisory boundary differences. |
| Measurements with invalid/unhashable attributes do not throw | Attribute tuple is used as a dictionary key | Gap | Attribute values such as lists can raise at runtime, violating error-handling guidance. |

### Async Callback Semantics

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| Callbacks invoked for the specific `MetricReader` | Producer invokes callbacks during each reader export | Partial | There is no reader-specific callback context/state; multiple readers share one producer and aggregation state. |
| Each callback can return multiple observations with attributes | `get_value()` returns the first observation value | Gap | All additional observations and all observation attributes are dropped. |
| Callback registration lifecycle | Callbacks only accepted at instrument creation | Gap | No callback registration/unregistration after creation. |
| Callback failures do not disrupt collection | Exceptions are caught and logged | Partial | If all callbacks fail, a `0.0` data point is emitted instead of no observation. |
| Callback timeout behavior | No timeout | Gap | Spec recommends callback timeout to prevent indefinite collection. |

### Aggregation, Temporality, and Data Model

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| Default aggregation by instrument kind | Sum, LastValue/Gauge, and ExplicitBucketHistogram are implemented | Partial | Default mappings are approximated, but not configurable per reader/exporter. |
| Drop aggregation | Not implemented | Gap | Required because Views require it. |
| ExponentialHistogram aggregation | Data classes exist, no aggregation path | Gap | Spec says SDK SHOULD provide it. Current SDK cannot produce it. |
| Delta and cumulative temporality selection | Always cumulative | Partial | No reader/exporter temporality selector; no delta state or start timestamp advancement. |
| Cardinality limit default and configuration | No cardinality limit | Gap | Spec SHOULD default to 2000 when otherwise unspecified. |
| Exemplars | Not implemented | Gap | SDK must provide ExemplarFilter/Reservoir hooks; default sampling SHOULD be on. |
| Duplicate metric identity handling | Simple duplicate identical-instrument case improved | Partial | No View conflict handling/warnings; incomplete scope and case normalization can still create non-compliant streams. |

### Readers and Exporters

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| MetricReader exposes `Collect`, `Shutdown`, and optional `ForceFlush` | Interface has `force_flush()`/`shutdown()`, no `collect()` | Gap | `ManualExportingMetricReader.force_flush()` acts as collect/export. |
| Multiple readers on same provider with independent state | Constructor accepts multiple readers | Partial | Shared producer state means no reader-specific aggregation/temporality/cardinality. |
| Periodic reader defaults: interval 60000 ms, timeout 30000 ms | `Config.metric_export_interval_ms` defaults to 10000; reader has no timeout arg | Gap | Env default differs from spec; `OTEL_METRIC_EXPORT_TIMEOUT` is not implemented. |
| Reader/exporter calls are not concurrent | No explicit synchronization around export | Gap | Background export and force flush can overlap on the same exporter. |
| ForceFlush returns failure on exporter failure and calls exporter `ForceFlush` | Readers ignore `ExportResult` and do not call exporter `force_flush()` | Gap | `PeriodicExportingMetricReader.force_flush()` always returns `True`. |
| Shutdown invokes readers and exporters | Provider calls reader shutdown | Partial | Manual reader shutdown is no-op; periodic reader does not call exporter shutdown. |
| Push Metric Exporter Export/ForceFlush/Shutdown | Base methods exist | Partial | No shutdown state; no export-after-shutdown guard; failures are not propagated through readers. |

## Logs

### API and Provider

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| `LoggerProvider.get_logger(name, version, schema_url, attributes)` uses full instrumentation scope | Arguments passed to upstream `ApiLogger` constructor | Partial | Export groups logs under `scopeLogs` with `"scope": {}`, so scope does not survive to OTLP. |
| Invalid logger names return working logger and log | Working logger returned | Partial | No invalid-name diagnostic. |
| Logger `emit()` accepts timestamp, observed timestamp, context, severity, body, attributes, event name, exception | Accepts most fields except exception | Partial | `context` and `event_name` are ignored; exception parameter is missing. |
| If context omitted, current context is used | Keyword emit uses current span | Partial | Explicit `context` argument is ignored. |
| `Logger.Enabled` | Not implemented | Gap | Also prevents spec LoggerConfig/filtering behavior. |

### SDK Semantics

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| LoggerConfig: enabled, minimum severity, trace based | Not implemented | Gap | No log filtering by config, severity, or sampled trace. |
| Observed timestamp defaults to current time | Keyword emit leaves it `None` if omitted | Gap | Encoder does not export observed timestamp at all. |
| Exception sets exception semantic attributes by default | No exception parameter/handling | Gap | Stdlib `exc_info` is not converted to OTel exception fields. |
| ReadableLogRecord trace context populated from resolved context | `MiniLogRecord` can store fields | Partial | Direct keyword path uses current span, not explicit context; encoder omits trace fields. |
| Custom processors and pipelines | Provider accepts one generic processor | Partial | No processor list/pipeline API. |
| LogRecordProcessor `OnEmit` operation | Uses generic `Processor.on_end()` | Partial | Naming and context parameter do not match spec. |
| Standard SDK implements simple and batch log processors | Generic `BatchProcessor` only | Gap | No SimpleLogRecordProcessor and no log-specific batch semantics. |
| Event-to-span-event bridge | Not implemented | Gap | Spec says this SHOULD be provided by SDK. |

### Exported Log Data Model

| Spec field | Current export | Status | Notes |
| --- | --- | --- | --- |
| `Timestamp` | `timeUnixNano` emitted, defaults to `"0"` when missing | Partial | No defaulting on emit path. |
| `ObservedTimestamp` | Not emitted | Gap | `observedTimeUnixNano` missing from OTLP JSON. |
| Trace context fields | Not emitted | Gap | `traceId`, `spanId`, and `flags` are omitted even if captured in `MiniLogRecord`. |
| Severity number/text | Emitted | Partial | Severity number uses enum `.value`, generally OK. |
| Body AnyValue | Always stringValue; falsey values become empty string | Gap | Structured bodies, `0`, `False`, and empty strings are not faithfully encoded. |
| Attributes | Emitted | Partial | No log attribute limits/dropped counts. |
| Event name | Not emitted | Gap | `event_name` arg is ignored. |
| Resource | Emitted | Compliant | Logs are grouped by resource. |
| Instrumentation scope | Empty `{}` | Gap | Logger scope is not encoded. |

## Resource

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| Resource is immutable | `Resource.get_attributes()` returns mutable dict | Gap | Attributes can change during resource lifetime. |
| SDK allows Resource creation from attributes and schema URL | `Resource(schema_url, attributes)` exists | Partial | No validation or immutable attribute representation. |
| Merge operation follows schema URL conflict rules | Merge overwrites attrs and prefers non-empty/new schema URL | Partial | Does not detect conflict when both schema URLs are non-empty and different. |
| Providers associate all telemetry with configured resource | Trace, metric, and log providers attach resource | Compliant | Export grouping includes resource. |
| SDK default resource attributes | `telemetry.sdk.language`, name, version, and `service.name` emitted | Partial | Spec points to semantic-convention defaults; detector-based defaults such as service/process/host support are incomplete. |
| Resource detectors | Not implemented as detector package model | Gap | The service detector requirement includes `OTEL_SERVICE_NAME` and `service.instance.id`; only service name is handled. |
| `OTEL_RESOURCE_ATTRIBUTES` parsing | Basic comma/equal split | Partial | No percent decoding for `,` or `=`, no invalid-value discard/error reporting. |
| `OTEL_SERVICE_NAME` precedence | Implemented | Compliant | Overrides `service.name` from `OTEL_RESOURCE_ATTRIBUTES`. |

## Context, TraceContext, and Baggage

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| TextMapPropagator inject/extract/fields | Implemented | Partial | Basic interface exists through upstream API base class. |
| Extract malformed data without throwing and preserve prior context | `traceparent` parser returns original context on invalid input | Compliant | Good behavior for invalid traceparent. |
| W3C TraceContext parses and validates `traceparent` and `tracestate` | Only `traceparent` parsed | Gap | `tracestate` is listed in fields but not extracted into `SpanContext`. |
| W3C TraceContext injects `traceparent` and valid `tracestate` | Only `traceparent` injected | Gap | `tracestate` is omitted even when non-empty. |
| Extracted remote context sets `is_remote=True` | Implemented | Compliant | Uses `NonRecordingSpan`. |
| Baggage API is available without SDK | Delegates to `opentelemetry.baggage` | Compliant | Upstream API handles context storage. |
| W3C Baggage propagator | Basic key/value parse/inject | Partial | Does not validate W3C key/value grammar, does not preserve metadata, and uses `quote_plus`/`unquote_plus` rather than a strict baggage encoder. |
| Global propagator configuration and `OTEL_PROPAGATORS` | Not implemented in `Config`/auto setup | Gap | No env parsing, deduping, disable/override path, or `opentelemetry.propagate` setup. |

## Configuration and Auto-Instrumentation

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| Empty env values treated as unset | `Env.get_int()` handles empty; `Env.get()` returns empty if present | Partial | Empty strings for string/enum vars may not fall back to defaults. |
| Boolean parsing only recognizes `true` as true and warns otherwise | `get_bool()` exists | Partial | No warnings; currently unused for spec vars. |
| Enum env vars are case-insensitive and warn on unknown values | Exporter names are used as exact entry point names | Gap | No case folding or warning semantics beyond not-found exporter warning. |
| `OTEL_SDK_DISABLED` | Not implemented | Gap | No no-op SDK setup path. |
| `OTEL_PROPAGATORS` | Not implemented | Gap | Default propagator is hard-coded in helper, not auto-configured. |
| `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG` | Not implemented | Gap | Sampler must be configurable for spec env support. |
| Batch processor env vars | `OTEL_BSP_MAX_EXPORT_BATCH_SIZE`, `OTEL_BSP_SCHEDULE_DELAY` | Partial | Missing `OTEL_BSP_EXPORT_TIMEOUT`, `OTEL_BSP_MAX_QUEUE_SIZE`, validation, and queue behavior. |
| Batch log record processor env vars | Reuses BSP vars for logs | Gap | Spec defines `OTEL_BLRP_*` separately. |
| Attribute/span/log limits env vars | Not implemented | Gap | No `OTEL_ATTRIBUTE_COUNT_LIMIT`, `OTEL_SPAN_*`, `OTEL_LOGRECORD_*`, etc. |
| Exporter selection env vars | `OTEL_TRACES_EXPORTER`, `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER` | Partial | Supports one exporter name only; no comma-separated multiple exporters; no deprecated `logging` alias. |
| Metric reader env vars | `OTEL_METRIC_EXPORT_INTERVAL` implemented | Partial | Default is 10000 ms instead of 60000 ms; `OTEL_METRIC_EXPORT_TIMEOUT` missing. |
| Auto-instrumentation CLI | `otel` wrapper injects `sitecustomize` path and discovers instrumentors | Partial | Useful subset, but no full environment-based SDK configuration, propagator setup, sampler setup, or disabled SDK handling. |

## OTLP Exporters

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| OTLP exporter endpoint options with signal-specific overrides | `_get_endpoint()` appends `/v1/{signal}` to base endpoint and uses signal override as-is | Partial | Handles the core path behavior, but URL edge cases, query strings, and HTTPS are not fully handled. |
| Default transport should be `http/protobuf`; support at least one of grpc/http-protobuf, preferably http-protobuf | Entry point `otlp` sends OTLP/JSON over HTTP | Partial | `http/json` is allowed, but spec default is `http/protobuf`; `OTEL_EXPORTER_OTLP_PROTOCOL` is ignored. |
| Headers env vars | Not implemented | Gap | No `OTEL_EXPORTER_OTLP_HEADERS` or signal-specific headers. |
| Compression env vars | Not implemented | Gap | No gzip option. |
| Timeout env vars | Exporter constructors default to 30 seconds | Partial | No `OTEL_EXPORTER_OTLP_TIMEOUT` or signal-specific timeout env parsing. |
| HTTP and HTTPS endpoint schemes | Uses `http.client.HTTPConnection` only | Gap | HTTPS endpoints will not use TLS. |
| Transient retry with exponential backoff and jitter | Retries 429/502/503/504 with exponential backoff | Partial | No jitter. |
| User-Agent header | Not emitted | Gap | Spec says OTLP exporters SHOULD identify exporter/language/version. |
| Export does not throw at runtime | Export attempts catch exceptions in retry wrapper | Compliant | HTTP request exceptions are converted to failure. |

## Error Handling and Concurrency

| Spec requirement | Current implementation | Status | Notes |
| --- | --- | --- | --- |
| API/SDK must not throw unhandled runtime exceptions | Many processor/exporter/callback paths catch exceptions | Partial | Instrument methods can throw on unhashable attributes; constructors can fail fast; some user callback/interface paths are protected. |
| Suppressed internal errors should be logged | Most catches call logger exception/warning | Compliant | Good pattern in exporters/processors/callbacks. |
| SDK allows user to change default error handling behavior | Not implemented | Gap | Spec requires configurable error handling for relevant errors. |
| Provider, tracer/meter/logger, processors, exporters safe for concurrent use | Limited locks in batcher and metric registry | Partial | Span mutation, metric aggregation state, logger emit processing, readers, and exporter calls are not fully synchronized or documented. |

## Existing Tests vs Spec Coverage

The test suite is useful for current behavior but does not yet prove spec compliance. It covers basic encoding, batching, propagator happy paths, resource env parsing, and metric aggregation. Important missing compliance tests include:

- Dropped sampled-out spans preserve valid trace context as non-recording spans.
- `MiniSpan.is_recording()`, post-end mutation guards, and idempotent `end()`.
- `start_span(start_time=...)` and `start_as_current_span(end_on_exit=False)`.
- Status and exception event OTLP encoding.
- Parent TraceState inheritance and `tracestate` propagation.
- Metric View behavior, case-insensitive instrument identity, duplicate conflict warnings, and full instrumentation scope.
- Async metric callbacks returning multiple observations with attributes.
- Histogram exact-boundary bucket placement.
- Metric reader export failure propagation, exporter shutdown, and no concurrent export calls.
- Log OTLP trace context, observed timestamp, event name, scope, falsey body values, and exception attributes.
- OTLP exporter env vars for protocol, headers, timeout, compression, and HTTPS.
- Error-handling tests for invalid attribute values and custom error handler behavior.

## Recommended Remediation Order

1. Fix trace correctness first: non-recording sampled-out spans, span lifecycle/idempotent end, start timestamp propagation, status export, exception event conventions, post-creation links, and `start_as_current_span()` parameter handling.

2. Fix log exported data model: include scope, observed timestamp, trace context fields, event name, AnyValue body encoding, and exception attributes. Add log-specific `OnEmit` processor shape after the data model is correct.

3. Add minimal Metrics SDK primitives: Views, reader `Collect`, exporter failure propagation, reader-specific temporality/aggregation hooks, correct async observations, and histogram boundary semantics.

4. Bring environment and OTLP exporter behavior in line with the spec: `OTEL_SDK_DISABLED`, sampler/env config, propagators, BLRP/BSP queue and timeout vars, metric export timeout/default interval, protocol/headers/compression/TLS, and retry jitter.

5. Harden error handling and concurrency: no runtime exceptions from invalid API inputs, immutable resources, synchronized exporter calls, thread-safe span/metric/log mutations, and a configurable error handler.
