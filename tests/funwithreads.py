import atexit
import threading
import time


class TelemetrySender:

    def __init__(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        atexit.register(self._stop)
        self._stop_event = threading.Event()

    def start(self):
        self.thread.start()

    def _run(self):
        while not self._stop_event.is_set():
            time.sleep(1)
            print(f"telemetry ({threading.currentThread().name})")

    def _stop(self):
        print(f"cleaning up ({threading.currentThread().name})")
        self._stop_event.set()
        self.thread.join()


class Greeter:

    def __init__(self, n):
        self.n = n

    def run(self):
        for i in range(self.n):
            time.sleep(1)
            print(f"greet {i}")


if __name__ == '__main__':
    t = TelemetrySender()
    t.start()

    g = Greeter(6)
    g.run()
    print("done")
