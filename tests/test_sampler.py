from otelmini.sampler import (
    AlwaysOffSampler,
    AlwaysOnSampler,
    Decision,
    TraceIdRatioBasedSampler,
)


def test_always_on_sampler():
    sampler = AlwaysOnSampler()
    result = sampler.should_sample(123456, "test-span")
    assert result.decision == Decision.RECORD_AND_SAMPLE


def test_always_off_sampler():
    sampler = AlwaysOffSampler()
    result = sampler.should_sample(123456, "test-span")
    assert result.decision == Decision.DROP


def test_trace_id_ratio_sampler_zero():
    sampler = TraceIdRatioBasedSampler(0.0)
    # Should never sample
    for i in range(100):
        result = sampler.should_sample(i, "test-span")
        assert result.decision == Decision.DROP


def test_trace_id_ratio_sampler_one():
    sampler = TraceIdRatioBasedSampler(1.0)
    # Should always sample
    for i in range(100):
        result = sampler.should_sample(i, "test-span")
        assert result.decision == Decision.RECORD_AND_SAMPLE


def test_trace_id_ratio_sampler_half():
    sampler = TraceIdRatioBasedSampler(0.5)
    # Check determinism: same trace_id always gets same result
    trace_id = 0xABCDEF123456789
    first_result = sampler.should_sample(trace_id, "span1")
    for _ in range(10):
        result = sampler.should_sample(trace_id, "span2")
        assert result.decision == first_result.decision


def test_trace_id_ratio_sampler_invalid_ratio():
    import pytest

    with pytest.raises(ValueError):
        TraceIdRatioBasedSampler(-0.1)
    with pytest.raises(ValueError):
        TraceIdRatioBasedSampler(1.1)
