"""Resource creation utilities."""

from __future__ import annotations

from otelmini.env import Config
from otelmini.types import Resource


def parse_resource_attributes(env_value: str) -> dict:
    """Parse OTEL_RESOURCE_ATTRIBUTES format: key1=value1,key2=value2"""
    if not env_value:
        return {}
    attributes = {}
    for pair in env_value.split(","):
        pair = pair.strip()
        if "=" in pair:
            key, value = pair.split("=", 1)
            attributes[key.strip()] = value.strip()
    return attributes


def create_default_resource(config: Config) -> Resource:
    """Create a resource with default SDK attributes and OTEL_RESOURCE_ATTRIBUTES."""
    from otelmini.__about__ import __version__

    # Start with env var attributes (lower priority)
    env_attrs = parse_resource_attributes(config.resource_attributes)

    # SDK attributes (higher priority, will override env)
    sdk_attrs = {
        "telemetry.sdk.language": "python",
        "telemetry.sdk.name": "otelmini",
        "telemetry.sdk.version": __version__,
        "service.name": config.service_name,
    }

    # Merge: env first, then SDK overwrites
    attributes = {**env_attrs, **sdk_attrs}
    return Resource(attributes=attributes)
