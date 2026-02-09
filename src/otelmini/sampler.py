from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from opentelemetry.trace.span import SpanContext

# Maximum value for 64-bit trace ID sampling bound
_MAX_TRACE_ID_BOUND = 2**64 - 1


class Decision(Enum):
    DROP = 0
    RECORD_AND_SAMPLE = 1


class SamplingResult:
    def __init__(self, decision: Decision):
        self.decision = decision


class Sampler:
    def should_sample(
        self, trace_id: int, name: str, parent_context: Optional[SpanContext] = None
    ) -> SamplingResult:
        raise NotImplementedError


class AlwaysOnSampler(Sampler):
    def should_sample(
        self, trace_id: int, name: str, parent_context: Optional[SpanContext] = None
    ) -> SamplingResult:
        return SamplingResult(Decision.RECORD_AND_SAMPLE)


class AlwaysOffSampler(Sampler):
    def should_sample(
        self, trace_id: int, name: str, parent_context: Optional[SpanContext] = None
    ) -> SamplingResult:
        return SamplingResult(Decision.DROP)


class TraceIdRatioBasedSampler(Sampler):
    def __init__(self, ratio: float):
        if not 0.0 <= ratio <= 1.0:
            raise ValueError("ratio must be between 0.0 and 1.0")
        self._bound = int(ratio * _MAX_TRACE_ID_BOUND)

    def should_sample(
        self, trace_id: int, name: str, parent_context: Optional[SpanContext] = None
    ) -> SamplingResult:
        # Use low 64 bits of trace_id for deterministic sampling
        if (trace_id & 0xFFFFFFFFFFFFFFFF) < self._bound:
            return SamplingResult(Decision.RECORD_AND_SAMPLE)
        return SamplingResult(Decision.DROP)


class ParentBasedSampler(Sampler):
    """Samples based on parent span's sampling decision.

    If there's no parent (root span), delegates to root sampler.
    If parent is sampled, delegates to remote_parent_sampled or local_parent_sampled.
    If parent is not sampled, delegates to remote_parent_not_sampled or local_parent_not_sampled.
    """

    def __init__(
        self,
        root: Sampler = None,
        remote_parent_sampled: Sampler = None,
        remote_parent_not_sampled: Sampler = None,
        local_parent_sampled: Sampler = None,
        local_parent_not_sampled: Sampler = None,
    ):
        self._root = root or AlwaysOnSampler()
        self._remote_parent_sampled = remote_parent_sampled or AlwaysOnSampler()
        self._remote_parent_not_sampled = (
            remote_parent_not_sampled or AlwaysOffSampler()
        )
        self._local_parent_sampled = local_parent_sampled or AlwaysOnSampler()
        self._local_parent_not_sampled = local_parent_not_sampled or AlwaysOffSampler()

    def should_sample(
        self, trace_id: int, name: str, parent_context: Optional[SpanContext] = None
    ) -> SamplingResult:
        from opentelemetry.trace import TraceFlags

        # No parent or invalid parent -> root span
        if parent_context is None or not parent_context.is_valid:
            return self._root.should_sample(trace_id, name, parent_context)

        # Check if parent was sampled
        parent_sampled = bool(parent_context.trace_flags & TraceFlags.SAMPLED)

        if parent_context.is_remote:
            if parent_sampled:
                return self._remote_parent_sampled.should_sample(
                    trace_id, name, parent_context
                )
            else:
                return self._remote_parent_not_sampled.should_sample(
                    trace_id, name, parent_context
                )
        else:
            if parent_sampled:
                return self._local_parent_sampled.should_sample(
                    trace_id, name, parent_context
                )
            else:
                return self._local_parent_not_sampled.should_sample(
                    trace_id, name, parent_context
                )
