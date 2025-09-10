#!/bin/bash

# kserve-vllm-mini Deployment Script
# Usage: ./deploy.sh [namespace]

set -e

NAMESPACE=${1:-"ml-prod"}
SERVICE_NAME="demo-llm"

echo "=== KServe vLLM Mini Deployment ==="
echo "Namespace: $NAMESPACE"
echo "Service name: $SERVICE_NAME"
echo ""

# Create namespace if it doesn't exist
echo "Creating namespace '$NAMESPACE'..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Deploy the InferenceService
echo "Deploying InferenceService..."
kubectl apply -f isvc.yaml

echo ""
echo "Waiting for InferenceService to be ready..."
kubectl wait --for=condition=Ready --timeout=300s inferenceservice/$SERVICE_NAME -n $NAMESPACE

echo ""
echo "=== DEPLOYMENT STATUS ==="
kubectl get inferenceservice $SERVICE_NAME -n $NAMESPACE

echo ""
echo "=== SERVICE URL ==="
SERVICE_URL=$(kubectl get inferenceservice $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.status.url}')
if [ -n "$SERVICE_URL" ]; then
  echo "Model endpoint: $SERVICE_URL"
  echo ""
  echo "=== TESTING CONNECTION ==="
  echo "Testing with a simple request..."
  
  # Test the endpoint
  kubectl run test-client --rm -i --restart=Never --image=curlimages/curl -- \
    curl -s -X POST -H 'Content-Type: application/json' \
    -d '{"text":"hello"}' "$SERVICE_URL" || echo "Connection test failed - service may still be starting up"
else
  echo "Service URL not available yet. Check the status above."
fi

echo ""
echo "=== NEXT STEPS ==="
echo "1. Run load test: ./load-test.sh '$SERVICE_URL'"
echo "2. Calculate costs: ./cost-calculator.sh /tmp/load-test-results.txt 1.00"
echo "3. Clean up: kubectl delete -f isvc.yaml && kubectl delete namespace $NAMESPACE"
