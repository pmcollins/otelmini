from __future__ import annotations

from enum import Enum


class Decision(Enum):
    DROP = 0
    RECORD_AND_SAMPLE = 1


class SamplingResult:
    def __init__(self, decision: Decision):
        self.decision = decision


class Sampler:
    def should_sample(self, trace_id: int, name: str) -> SamplingResult:
        raise NotImplementedError


class AlwaysOnSampler(Sampler):
    def should_sample(self, trace_id: int, name: str) -> SamplingResult:
        return SamplingResult(Decision.RECORD_AND_SAMPLE)


class AlwaysOffSampler(Sampler):
    def should_sample(self, trace_id: int, name: str) -> SamplingResult:
        return SamplingResult(Decision.DROP)


class TraceIdRatioBasedSampler(Sampler):
    def __init__(self, ratio: float):
        if not 0.0 <= ratio <= 1.0:
            raise ValueError("ratio must be between 0.0 and 1.0")
        self._bound = int(ratio * (2**64 - 1))

    def should_sample(self, trace_id: int, name: str) -> SamplingResult:
        # Use low 64 bits of trace_id for deterministic sampling
        if (trace_id & 0xFFFFFFFFFFFFFFFF) < self._bound:
            return SamplingResult(Decision.RECORD_AND_SAMPLE)
        return SamplingResult(Decision.DROP)
