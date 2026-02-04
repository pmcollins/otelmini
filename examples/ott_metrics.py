import time
from pathlib import Path
from typing import Mapping, Optional, Sequence

from otelmini.metric import ManualExportingMetricReader, MeterProvider, ConsoleMetricExporter

if __name__ == '__main__':
    exporter = ConsoleMetricExporter()
    reader = ManualExportingMetricReader(exporter=exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter("my-meter")
    counter = meter.create_counter("x")
    counter.add(42)
    time.sleep(1)
    reader.force_flush()
    time.sleep(1)


class MetricsOtelTest:
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
