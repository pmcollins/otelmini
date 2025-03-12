# otelmini

[![PyPI - Version](https://img.shields.io/pypi/v/otelmini.svg)](https://pypi.org/project/otelmini)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/otelmini.svg)](https://pypi.org/project/otelmini)

-----

**Table of Contents**

- [Installation](#installation)
- [License](#license)

## Installation

The package can be installed in two ways:

### Basic Installation (~140 KB)
For basic logging functionality with console output:
```console
pip install otelmini
```

### gRPC Installation (~12 MB)
For gRPC export support, install with the `grpc` extra:
```console
pip install otelmini[grpc]
```

The gRPC installation includes additional dependencies:
- grpcio (~11.3 MB)
- googleapis-common-protos (~293 KB)
- opentelemetry-proto (~55 KB)
- protobuf (~417 KB)
- oteltest (~13 KB)

Choose the basic installation if you only need console logging, or install with gRPC support if you need to export logs to an OpenTelemetry collector.

## License

`otelmini` is distributed under the terms of the [Apache-2.0](https://spdx.org/licenses/Apache-2.0.html) license.
