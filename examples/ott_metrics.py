from pathlib import Path
from typing import Mapping, Optional, Sequence

if __name__ == '__main__':
    pass


class MetricsOtelTest:
    def environment_variables(self) -> Mapping[str, str]:
        return {}

    def requirements(self) -> Sequence[str]:
        parent = str(Path(__file__).resolve().parent.parent)
        return (parent,)

    def wrapper_command(self) -> str:
        return ""

    def is_http(self) -> bool:
        return False

    def on_start(self) -> Optional[float]:
        pass

    def on_stop(self, tel, stdout: str, stderr: str, returncode: int) -> None:
        pass
