from dataclasses import dataclass
from typing import Any, Callable, Optional

from opentelemetry.trace import Span as ApiSpan
from opentelemetry.trace.span import SpanContext
from opentelemetry.util.types import Attributes


@dataclass(frozen=True)
class InstrumentationScope:
    name: str
    version: Optional[str] = None
    schema_url: Optional[str] = None
    attributes: Optional[Attributes] = None


class Resource:
    def __init__(self, schema_url: str = ""):
        self._schema_url = schema_url
        self._attributes = {}

    def get_attributes(self):
        return self._attributes

    def get_schema_url(self):
        return self._schema_url

    def __getstate__(self):
        return {"schema_url": self._schema_url, "attributes": self._attributes}

    def __setstate__(self, state):
        self._schema_url = state["schema_url"]
        self._attributes = state["attributes"]


class MiniSpan(ApiSpan):
    def __init__(
        self,
        name: str,
        span_context: SpanContext,
        resource: Resource,
        instrumentation_scope: InstrumentationScope,
        on_end_callback: Callable[["MiniSpan"], None],
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

    def set_attributes(self, attributes):
        self._attributes.update(attributes)

    def set_attribute(self, key: str, value):
        self._attributes[key] = value

    def add_event(self, name: str, attributes=None, timestamp: Optional[int] = None) -> None:
        self._events.append((name, attributes, timestamp))

    def update_name(self, name: str) -> None:
        self._name = name

    def is_recording(self) -> bool:
        return self._status is None

    def set_status(self, status, description: Optional[str] = None) -> None:
        self._status = status
        self._status_description = description

    def record_exception(
        self,
        exception: BaseException,
        attributes=None,
        timestamp: Optional[int] = None,
        escaped: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        self._events.append((exception.__class__.__name__, attributes, timestamp))

    def end(self, end_time: Optional[int] = None) -> None:
        self._on_end_callback(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.get_name(),
            "span_context": self.get_span_context(),
            "resource": self.get_resource(),
            "instrumentation_scope": self.get_instrumentation_scope(),
            "attributes": self._attributes,
            "events": self._events,
            "status": self._status,
            "status_description": self._status_description,
        }

    def __str__(self) -> str:
        return f"MiniSpan(name='{self._name}', span_context={self._span_context})"

    @classmethod
    def from_dict(cls, data: dict[str, Any], on_end_callback: Callable[["MiniSpan"], None]) -> "MiniSpan":
        return cls(
            name=data["name"],
            span_context=data["span_context"],
            resource=data["resource"],
            instrumentation_scope=data["instrumentation_scope"],
            on_end_callback=on_end_callback,
        )
