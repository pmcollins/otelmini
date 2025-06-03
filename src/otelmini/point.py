# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# pylint: disable=unused-import

from dataclasses import asdict, dataclass, field
from json import dumps, loads
from typing import Optional, Sequence, Union
from enum import Enum

from opentelemetry.util.types import Attributes

from otelmini.types import InstrumentationScope, Resource


class AggregationTemporality(Enum):
    CUMULATIVE = 2
    DELTA = 1


@dataclass(frozen=True)
class NumberDataPoint:

    attributes: Attributes
    start_time_unix_nano: int
    time_unix_nano: int
    value: Union[int, float]
    # exemplars: Sequence[Exemplar] = field(default_factory=list)

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(asdict(self), indent=indent)


@dataclass(frozen=True)
class HistogramDataPoint:

    attributes: Attributes
    start_time_unix_nano: int
    time_unix_nano: int
    count: int
    sum: Union[int, float]
    bucket_counts: Sequence[int]
    explicit_bounds: Sequence[float]
    min: float
    max: float
    # exemplars: Sequence[Exemplar] = field(default_factory=list)

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(asdict(self), indent=indent)


@dataclass(frozen=True)
class Buckets:
    offset: int
    bucket_counts: Sequence[int]


@dataclass(frozen=True)
class ExponentialHistogramDataPoint:

    attributes: Attributes
    start_time_unix_nano: int
    time_unix_nano: int
    count: int
    sum: Union[int, float]
    scale: int
    zero_count: int
    positive: Buckets
    negative: Buckets
    flags: int
    min: float
    max: float
    # exemplars: Sequence[Exemplar] = field(default_factory=list)

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(asdict(self), indent=indent)


@dataclass(frozen=True)
class ExponentialHistogram:

    data_points: Sequence[ExponentialHistogramDataPoint]
    aggregation_temporality: AggregationTemporality

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(
            {
                "data_points": [
                    loads(data_point.to_json(indent=indent))
                    for data_point in self.data_points
                ],
                "aggregation_temporality": self.aggregation_temporality,
            },
            indent=indent,
        )


@dataclass(frozen=True)
class Sum:

    data_points: Sequence[NumberDataPoint]
    aggregation_temporality: AggregationTemporality
    is_monotonic: bool

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(
            {
                "data_points": [
                    loads(data_point.to_json(indent=indent))
                    for data_point in self.data_points
                ],
                "aggregation_temporality": self.aggregation_temporality,
                "is_monotonic": self.is_monotonic,
            },
            indent=indent,
        )


@dataclass(frozen=True)
class Gauge:

    data_points: Sequence[NumberDataPoint]

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(
            {
                "data_points": [
                    loads(data_point.to_json(indent=indent))
                    for data_point in self.data_points
                ],
            },
            indent=indent,
        )


@dataclass(frozen=True)
class Histogram:
    data_points: Sequence[HistogramDataPoint]
    aggregation_temporality: AggregationTemporality

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(
            {
                "data_points": [
                    loads(data_point.to_json(indent=indent))
                    for data_point in self.data_points
                ],
                "aggregation_temporality": self.aggregation_temporality,
            },
            indent=indent,
        )


# pylint: disable=invalid-name
DataT = Union[Sum, Gauge, Histogram, ExponentialHistogram]
DataPointT = Union[
    NumberDataPoint, HistogramDataPoint, ExponentialHistogramDataPoint
]


@dataclass(frozen=True)
class Metric:
    name: str
    description: Optional[str]
    unit: Optional[str]
    data: DataT

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(
            {
                "name": self.name,
                "description": self.description or "",
                "unit": self.unit or "",
                "data": loads(self.data.to_json(indent=indent)),
            },
            indent=indent,
        )


@dataclass(frozen=True)
class ScopeMetrics:
    scope: InstrumentationScope
    metrics: Sequence[Metric]
    schema_url: str

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(
            {
                "scope": loads(self.scope.to_json(indent=indent)),
                "metrics": [
                    loads(metric.to_json(indent=indent))
                    for metric in self.metrics
                ],
                "schema_url": self.schema_url,
            },
            indent=indent,
        )


@dataclass(frozen=True)
class ResourceMetrics:
    resource: Resource
    scope_metrics: Sequence[ScopeMetrics]
    schema_url: str

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(
            {
                "resource": loads(self.resource.to_json(indent=indent)),
                "scope_metrics": [
                    loads(scope_metrics.to_json(indent=indent))
                    for scope_metrics in self.scope_metrics
                ],
                "schema_url": self.schema_url,
            },
            indent=indent,
        )


@dataclass(frozen=True)
class MetricsData:
    resource_metrics: Sequence[ResourceMetrics]

    def to_json(self, indent: Optional[int] = 4) -> str:
        return dumps(
            {
                "resource_metrics": [
                    loads(resource_metrics.to_json(indent=indent))
                    for resource_metrics in self.resource_metrics
                ]
            },
            indent=indent,
        )
