import multiprocessing

from otelmini.processor import Processor
from otelmini.trace import GrpcSpanExporter, MiniSpan


def run_remote(exporter: GrpcSpanExporter, queue: multiprocessing.Queue) -> None:
    exporter.init_grpc()
    for i in range(12):
        span_dict = queue.get(timeout=4)
        span = MiniSpan.from_dict(span_dict, on_end_callback=lambda s: None)
        exporter.export([span])


class RemoteBatchProcessor(Processor[MiniSpan]):
    def __init__(self, exporter: GrpcSpanExporter, batch_size, interval_seconds):
        self.q = multiprocessing.Queue()
        multiprocessing.Process(target=run_remote, args=(exporter, self.q)).start()

    def on_start(self, item: MiniSpan) -> None:
        pass

    def on_end(self, item: MiniSpan) -> None:
        self.q.put(item.to_dict())

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

