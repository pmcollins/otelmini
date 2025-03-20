import multiprocessing
import time
from typing import Sequence, Dict, Any

from otelmini._lib import ExportResult
from otelmini.processor import Exporter, Processor, T
from otelmini.trace import MiniSpan, MiniTracer

N = 4


class FunExporter(Exporter[MiniSpan]):
    def __init__(self):
        print("initializing")
        self.connected = False
        self.test_field = "test value"

    def connect(self):
        print("connecting...")
        self.connected = True

    def __setstate__(self, state):
        print("setting state")
        self.__dict__.update(state)
        self.connect()

    def export(self, items: Sequence[T]) -> ExportResult:
        if not self.connected:
            print("not connected, skipping export")
            return ExportResult.FAILURE
        print(f"exporting: {items}")
        return ExportResult.SUCCESS


def run_remote(q: multiprocessing.Queue, exporter: FunExporter):
    print(exporter)
    print(f"test_field in child: {exporter.test_field}")
    while True:
        try:
            item = q.get(timeout=1)
            print(f"run: processing item {item}")
        except multiprocessing.TimeoutError:
            if not multiprocessing.parent_process().is_alive():
                break
        except Exception as e:
            print(f"run: error {e}")
            break


class RemoteProcessor(Processor[MiniSpan]):
    def __init__(self, exporter: Exporter):
        self.exporter = exporter
        self.queue = multiprocessing.Queue()
        multiprocessing.Process(target=run_remote, args=(self.queue, self.exporter)).start()

    def on_start(self, item: MiniSpan) -> None:
        print(f"on_start: {item}")

    def on_end(self, item: MiniSpan) -> None:
        print(f"on_end: {item}")
        self.queue.put(item.to_dict())


def main():
    tracer = MiniTracer(RemoteProcessor(FunExporter()))
    for i in range(N):
        with tracer.start_span("foo") as span:
            time.sleep(1)
            print(".")


if __name__ == "__main__":
    multiprocessing.set_start_method('spawn')
    main()
