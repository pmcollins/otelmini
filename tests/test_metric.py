from typing import Sequence

from otelmini._lib import Exporter, T, ExportResult
from otelmini.metric import ManualExportingMetricReader, MeterProvider


def test_metric():
    exporter = FakeExporter()
    reader = ManualExportingMetricReader(exporter)
    meter_provider = MeterProvider(metric_readers=(reader,))
    meter = meter_provider.get_meter(name="my-meter")
    counter = meter.create_counter(name="x")
    counter.add(42)
    reader.force_flush()
    assert len(exporter.get_exports())


class FakeExporter(Exporter):
    def __init__(self):
        self.exports = []

    def export(self, items: Sequence[T]) -> ExportResult:
        self.exports.append(items)
        return ExportResult.SUCCESS

    def get_exports(self):
        return self.exports
