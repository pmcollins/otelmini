from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Sequence, TypeVar

from otelmini._grpclib import GrpcExportResult

T = TypeVar("T")


class Exporter(ABC, Generic[T]):
    @abstractmethod
    def export(self, items: Sequence[T]) -> GrpcExportResult:
        pass
