from otelmini.env import Config, Env


def test_config_defaults():
    config = Config(Env({}))
    assert config.service_name == "unknown_service"
    assert config.resource_attributes == ""
    assert config.bsp_batch_size == 512
    assert config.bsp_schedule_delay_ms == 5000
    assert config.exporter_endpoint == "http://localhost:4318"
    assert config.metric_export_interval_ms == 10000


def test_config_from_env():
    config = Config(Env({
        "OTEL_SERVICE_NAME": "my-service",
        "OTEL_RESOURCE_ATTRIBUTES": "env=prod",
        "OTEL_BSP_MAX_EXPORT_BATCH_SIZE": "256",
        "OTEL_BSP_SCHEDULE_DELAY": "1000",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4318",
        "OTEL_METRIC_EXPORT_INTERVAL": "5000",
    }))
    assert config.service_name == "my-service"
    assert config.resource_attributes == "env=prod"
    assert config.bsp_batch_size == 256
    assert config.bsp_schedule_delay_ms == 1000
    assert config.exporter_endpoint == "http://collector:4318"
    assert config.metric_export_interval_ms == 5000


def test_config_invalid_int_uses_default():
    config = Config(Env({
        "OTEL_BSP_MAX_EXPORT_BATCH_SIZE": "not-a-number",
    }))
    assert config.bsp_batch_size == 512  # Falls back to default


def test_config_as_dict():
    config = Config(Env({"OTEL_SERVICE_NAME": "test"}))
    d = config.as_dict()
    assert d["service_name"] == "test"
    assert "bsp_batch_size" in d
    assert "exporter_endpoint" in d


def test_config_repr():
    config = Config(Env({"OTEL_SERVICE_NAME": "test"}))
    r = repr(config)
    assert "Config(" in r
    assert "test" in r


def test_config_signal_specific_endpoints():
    config = Config(Env({
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://default:4318",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://traces:4318/v1/traces",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://metrics:4318/v1/metrics",
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": "http://logs:4318/v1/logs",
    }))
    assert config.exporter_endpoint == "http://default:4318"
    assert config.exporter_traces_endpoint == "http://traces:4318/v1/traces"
    assert config.exporter_metrics_endpoint == "http://metrics:4318/v1/metrics"
    assert config.exporter_logs_endpoint == "http://logs:4318/v1/logs"
