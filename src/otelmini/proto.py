from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.metrics.v1 import metrics_pb2 as pb2
from opentelemetry.proto.resource.v1.resource_pb2 import Resource as PB2Resource

from otelmini.point import MetricsData


def pb_encode_metrics(data: MetricsData) -> ExportMetricsServiceRequest:
    resource_metrics_dict = {}

    for resource_metrics in data.resource_metrics:
        _encode_resource_metrics(resource_metrics, resource_metrics_dict)

    resource_data = []
    for (sdk_resource, scope_data) in resource_metrics_dict.items():
        resource_data.append(
            pb2.ResourceMetrics(
                resource=PB2Resource(attributes=_encode_attributes(sdk_resource.attributes)),
                scope_metrics=scope_data.values(),
                schema_url=sdk_resource.schema_url,
            )
        )
    return ExportMetricsServiceRequest(resource_metrics=resource_data)


def _encode_resource_metrics(resource_metrics, resource_metrics_dict):
    pass


def _encode_attributes(attributes):
    pass
