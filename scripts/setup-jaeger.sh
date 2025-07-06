#!/bin/bash

# Setup Jaeger Tracing for Hand Gesture Detection Service
# This script deploys Jaeger to Kubernetes using Helm charts

set -e

echo "🔍 Setting up Jaeger Tracing with Helm..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed or not in PATH"
    exit 1
fi

# Check if helm is available
if ! command -v helm &> /dev/null; then
    print_error "helm is not installed or not in PATH"
    exit 1
fi

# Check if we can connect to the cluster
if ! kubectl cluster-info &> /dev/null; then
    print_error "Cannot connect to Kubernetes cluster"
    exit 1
fi

print_status "Connected to Kubernetes cluster"

# Create tracing namespace
print_status "Creating tracing namespace..."
kubectl create namespace tracing --dry-run=client -o yaml | kubectl apply -f -
print_success "Tracing namespace ready"

# Add Jaeger Helm repository
print_status "Adding Jaeger Helm repository..."
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
helm repo update
print_success "Jaeger Helm repository added"

# Deploy Jaeger using Helm chart
print_status "Deploying Jaeger with Helm..."
helm upgrade --install jaeger jaegertracing/jaeger \
  --namespace tracing \
  --values helm-charts/jaeger/values.yaml \
  --history-max 3 \
  --wait \
  --timeout 300s

print_success "Jaeger deployed successfully"

# Wait for Jaeger to be ready
print_status "Waiting for Jaeger to be ready..."
kubectl wait --for=condition=ready --timeout=300s pod -l app.kubernetes.io/instance=jaeger -n tracing

print_success "Jaeger is ready"

# Get Jaeger UI URL
print_status "Getting Jaeger UI access information..."

# Check if ingress is configured
JAEGER_HOST=$(kubectl get ingress -n tracing -o jsonpath='{.items[0].spec.rules[0].host}' 2>/dev/null || echo "")

if [ -n "$JAEGER_HOST" ]; then
    print_success "Jaeger UI available at: http://$JAEGER_HOST"
else
    print_warning "Jaeger ingress not found. You can access Jaeger UI via port-forward:"
    echo "kubectl port-forward -n tracing svc/jaeger-query 16686:16686"
    echo "Then access: http://localhost:16686"
fi

# Show Jaeger services
print_status "Jaeger services:"
kubectl get svc -n tracing -l app.kubernetes.io/instance=jaeger

# Show Jaeger pods
print_status "Jaeger pods:"
kubectl get pods -n tracing -l app.kubernetes.io/instance=jaeger

# Display connection information for applications
print_success "Jaeger setup complete!"
print_status "Application configuration:"
echo "JAEGER_AGENT_HOST: jaeger-agent.tracing.svc.cluster.local"
echo "JAEGER_AGENT_PORT: 6831"
echo "OTEL_EXPORTER_JAEGER_ENDPOINT: http://jaeger-collector.tracing.svc.cluster.local:14268/api/traces"
echo ""
print_status "Next steps:"
echo "1. Deploy your application with tracing enabled:"
echo "   helm upgrade --install hand-gesture ./helm-charts/asl -n model-serving"
echo ""
echo "2. Generate some traffic to your application"
echo ""
echo "3. View traces in Jaeger UI"
echo ""
echo "4. Check application logs for tracing status:"
echo "   kubectl logs -n model-serving deployment/hand-gesture-deployment" 