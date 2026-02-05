from dataclasses import dataclass
import time
from typing import Any, Callable, Optional
import json

from opentelemetry.trace import Span as ApiSpan
from opentelemetry.trace.span import SpanContext
from opentelemetry.util.types import Attributes


def _time_ns() -> int:
    """Get current time in nanoseconds."""
    return time.time_ns()


@dataclass(frozen=True)
class InstrumentationScope:
    name: str
    version: Optional[str] = None
    schema_url: Optional[str] = None
    attributes: Optional[Attributes] = None

    def to_dict(self):
        return {
            "name": self.name,
            "version": self.version,
            "schema_url": self.schema_url,
            "attributes": self.attributes,
        }

    def to_json(self, indent: int = 4) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class Resource:
    def __init__(self, schema_url: str = "", attributes: Optional[dict] = None):
        self._schema_url = schema_url
        self._attributes = attributes or {}

    def get_attributes(self):
        return self._attributes

    def get_schema_url(self):
        return self._schema_url

    def to_dict(self):
        return {
            "schema_url": self._schema_url,
            "attributes": self._attributes,
        }

    def to_json(self, indent: int = 4) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def __getstate__(self):
        return {"schema_url": self._schema_url, "attributes": self._attributes}

    def __setstate__(self, state):
        self._schema_url = state["schema_url"]
        self._attributes = state["attributes"]


def span_context_to_dict(span_context: SpanContext) -> dict:
    return {
        "trace_id": span_context.trace_id,
        "span_id": span_context.span_id,
        "trace_flags": int(getattr(span_context, "trace_flags", 0)),
        "is_remote": getattr(span_context, "is_remote", False),
        "tracestate": str(getattr(span_context, "trace_state", "")),
    }


class MiniSpan(ApiSpan):
    def __init__(
        self,
        name: str,
        span_context: SpanContext,
        resource: Resource,
        instrumentation_scope: InstrumentationScope,
        on_end_callback: Callable[["MiniSpan"], None],
        parent_span_id: Optional[int] = None,
        start_time: Optional[int] = None,
    ):
        self._name = name
        self._span_context = span_context
        self._resource = resource
        self._instrumentation_scope = instrumentation_scope
        self._attributes = {}
        self._events = []
        self._status = None
        self._status_description = None
        self._on_end_callback = on_end_callback
        self._parent_span_id = parent_span_id
        self._start_time = start_time if start_time is not None else _time_ns()
        self._end_time: Optional[int] = None

    def get_parent_span_id(self) -> Optional[int]:
        return self._parent_span_id

    def get_start_time(self) -> int:
        return self._start_time

    def get_end_time(self) -> Optional[int]:
        return self._end_time

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end()

    def get_span_context(self) -> SpanContext:
        return self._span_context

    def get_name(self):
        return self._name

    def get_resource(self):
        return self._resource

    def get_instrumentation_scope(self):
        return self._instrumentation_scope

    def get_attributes(self):
        return self._attributes

    def get_events(self):
        return self._events

    def get_status(self):
        return self._status

    def get_status_description(self):
        return self._status_description

    def set_attributes(self, attributes: Attributes) -> None:
        self._attributes.update(attributes)

    def set_attribute(self, key: str, value: Any) -> None:
        self._attributes[key] = value

    def add_event(
        self, name: str, attributes: Optional[Attributes] = None, timestamp: Optional[int] = None
    ) -> None:
        if timestamp is None:
            timestamp = _time_ns()
        self._events.append((name, attributes, timestamp))

    def update_name(self, name: str) -> None:
        self._name = name

    def is_recording(self) -> bool:
        return self._status is None

    def set_status(self, status: Any, description: Optional[str] = None) -> None:
        self._status = status
        self._status_description = description

    def record_exception(
        self,
        exception: BaseException,
        attributes: Optional[Attributes] = None,
        timestamp: Optional[int] = None,
        escaped: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        if timestamp is None:
            timestamp = _time_ns()
        self._events.append((exception.__class__.__name__, attributes, timestamp))

    def end(self, end_time: Optional[int] = None) -> None:
        self._end_time = end_time if end_time is not None else _time_ns()
        self._on_end_callback(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.get_name(),
            "span_context": span_context_to_dict(self.get_span_context()),
            "resource": self.get_resource().to_dict(),
            "instrumentation_scope": self.get_instrumentation_scope().to_dict(),
            "attributes": self._attributes,
            "events": self._events,
            "status": self._status,
            "status_description": self._status_description,
        }

    def __str__(self) -> str:
        return f"MiniSpan(name='{self._name}', span_context={self._span_context})"

    @classmethod
    def from_dict(cls, data: dict[str, Any], on_end_callback: Callable[["MiniSpan"], None]) -> "MiniSpan":
        span_context_dict = data["span_context"]
        span_context = SpanContext(
            trace_id=span_context_dict["trace_id"],
            span_id=span_context_dict["span_id"],
            is_remote=span_context_dict.get("is_remote", False),
            trace_flags=span_context_dict.get("trace_flags", 0),
            trace_state=span_context_dict.get("tracestate", ""),
        )
        resource_dict = data["resource"]
        resource = Resource(schema_url=resource_dict.get("schema_url", ""))
        resource._attributes = resource_dict.get("attributes", {})
        instr_scope_dict = data["instrumentation_scope"]
        instrumentation_scope = InstrumentationScope(
            name=instr_scope_dict["name"],
            version=instr_scope_dict.get("version"),
            schema_url=instr_scope_dict.get("schema_url"),
            attributes=instr_scope_dict.get("attributes"),
        )
        return cls(
            name=data["name"],
            span_context=span_context,
            resource=resource,
            instrumentation_scope=instrumentation_scope,
            on_end_callback=on_end_callback,
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
