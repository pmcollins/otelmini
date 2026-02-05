"""Resource creation utilities."""
from __future__ import annotations

import os

from otelmini.types import Resource


def create_default_resource() -> Resource:
    """Create a resource with default SDK attributes."""
    import otelmini
    service_name = os.environ.get("OTEL_SERVICE_NAME", "unknown_service")
    return Resource(attributes={
        "telemetry.sdk.language": "python",
        "telemetry.sdk.name": "otelmini",
        "telemetry.sdk.version": getattr(otelmini, "__version__", "0.0.1"),
        "service.name": service_name,
    })
