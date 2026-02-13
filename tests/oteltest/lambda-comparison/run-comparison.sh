#!/bin/bash
# Run cold start comparison between otelmini and opentelemetry-sdk
#
# Prerequisites:
#   - Docker running
#   - AWS SAM CLI installed: brew install aws-sam-cli
#
# Usage:
#   ./run-comparison.sh

set -e

cd "$(dirname "$0")"

echo "=== Building functions (in container) ==="
sam build --use-container

echo ""
echo "=== Package sizes ==="
echo "otelmini:"
du -sh .aws-sam/build/OtelMiniFunction/
echo ""
echo "opentelemetry-sdk:"
du -sh .aws-sam/build/OtelPythonFunction/

echo ""
echo "=== Cold start: otelmini ==="
sam local invoke OtelMiniFunction -e event.json 2>/dev/null | jq -r '.body' | jq .

echo ""
echo "=== Cold start: opentelemetry-sdk ==="
sam local invoke OtelPythonFunction -e event.json 2>/dev/null | jq -r '.body' | jq .

echo ""
echo "=== Running multiple invocations for average ==="
echo "otelmini (3 runs):"
for i in 1 2 3; do
    sam local invoke OtelMiniFunction -e event.json 2>/dev/null | jq -r '.body' | jq -r '.timing.total_init_ms'
done

echo ""
echo "opentelemetry-sdk (3 runs):"
for i in 1 2 3; do
    sam local invoke OtelPythonFunction -e event.json 2>/dev/null | jq -r '.body' | jq -r '.timing.total_init_ms'
done
