import time
from pathlib import Path
from typing import Mapping, Optional, Sequence

from opentelemetry.metrics import Observation
from otelmini.metric import ManualExportingMetricReader, MeterProvider, HttpMetricExporter

# Simulated CPU usage value
_cpu_usage = 65.5


def cpu_callback():
    """Callback that returns simulated CPU usage."""
    return [Observation(value=_cpu_usage)]


if __name__ == '__main__':
    exporter = HttpMetricExporter()
    reader = ManualExportingMetricReader(exporter=exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter("my-meter")
    gauge = meter.create_observable_gauge(
        "cpu_usage",
        callbacks=[cpu_callback],
        unit="%",
        description="CPU usage percentage"
    )
    time.sleep(1)
    reader.force_flush()
    time.sleep(1)


class ObservableGaugeOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        parent = str(Path(__file__).resolve().parent.parent)
        return (parent,)

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return True

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        from oteltest.telemetry import count_metrics

        assert count_metrics(tel)
