import os

from otelmini.resource import create_default_resource, parse_resource_attributes
from otelmini.types import Resource


def test_parse_resource_attributes_empty():
    assert parse_resource_attributes("") == {}
    assert parse_resource_attributes(None) == {}


def test_parse_resource_attributes_single():
    result = parse_resource_attributes("key=value")
    assert result == {"key": "value"}


def test_parse_resource_attributes_multiple():
    result = parse_resource_attributes("key1=value1,key2=value2")
    assert result == {"key1": "value1", "key2": "value2"}


def test_parse_resource_attributes_with_spaces():
    result = parse_resource_attributes(" key1 = value1 , key2 = value2 ")
    assert result == {"key1": "value1", "key2": "value2"}


def test_parse_resource_attributes_value_with_equals():
    result = parse_resource_attributes("key=value=with=equals")
    assert result == {"key": "value=with=equals"}


def test_create_default_resource_includes_env_attributes(monkeypatch):
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "env=prod,region=us-east-1")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "test-service")

    resource = create_default_resource()
    attrs = resource.get_attributes()

    # Check env attributes are present
    assert attrs["env"] == "prod"
    assert attrs["region"] == "us-east-1"
    # Check SDK attributes are present
    assert attrs["service.name"] == "test-service"
    assert attrs["telemetry.sdk.name"] == "otelmini"


def test_create_default_resource_sdk_attrs_override_env(monkeypatch):
    # If someone sets service.name via OTEL_RESOURCE_ATTRIBUTES,
    # OTEL_SERVICE_NAME should take precedence
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.name=from-env-attrs")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "from-service-name-var")

    resource = create_default_resource()
    attrs = resource.get_attributes()

    assert attrs["service.name"] == "from-service-name-var"


def test_resource_merge_attributes():
    r1 = Resource(attributes={"a": "1", "b": "2"})
    r2 = Resource(attributes={"b": "override", "c": "3"})

    merged = r1.merge(r2)
    attrs = merged.get_attributes()

    assert attrs["a"] == "1"
    assert attrs["b"] == "override"  # r2 takes precedence
    assert attrs["c"] == "3"


def test_resource_merge_schema_url():
    r1 = Resource(schema_url="https://schema1.example.com", attributes={})
    r2 = Resource(schema_url="https://schema2.example.com", attributes={})

    merged = r1.merge(r2)
    assert merged.get_schema_url() == "https://schema2.example.com"


def test_resource_merge_schema_url_empty_other():
    r1 = Resource(schema_url="https://schema1.example.com", attributes={})
    r2 = Resource(schema_url="", attributes={})

    merged = r1.merge(r2)
    assert merged.get_schema_url() == "https://schema1.example.com"


def test_resource_merge_returns_new_resource():
    r1 = Resource(attributes={"a": "1"})
    r2 = Resource(attributes={"b": "2"})

    merged = r1.merge(r2)

    # Original resources should be unchanged
    assert r1.get_attributes() == {"a": "1"}
    assert r2.get_attributes() == {"b": "2"}
    assert merged.get_attributes() == {"a": "1", "b": "2"}
