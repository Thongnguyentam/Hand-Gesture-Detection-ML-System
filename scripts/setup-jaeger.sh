#!/bin/bash

# Jaeger Tracing Setup Script
# This script can clean up existing Jaeger resources and reinstall the entire stack

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="tracing"
HELM_TIMEOUT="10m"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

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

# Function to check if command exists
check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 is not installed. Please install it first."
        exit 1
    fi
}

# Function to wait for pods to be ready
wait_for_pods() {
    local namespace=$1
    local label_selector=$2
    local timeout=${3:-300} # 300 seconds = 5 minutes
    
    print_status "Waiting for pods with label '$label_selector' in namespace '$namespace' to be ready..."
    
    if kubectl wait --for=condition=ready pod -l "$label_selector" -n "$namespace" --timeout="${timeout}s" 2>/dev/null; then
        print_success "Pods are ready!"
    else
        print_warning "Timeout waiting for pods to be ready. Continuing anyway..."
    fi
}

# Function to clean up Jaeger stack
cleanup_jaeger() {
    print_status "🧹 Cleaning up existing Jaeger stack..."
    
    # Remove Helm release
    print_status "Removing Helm release..."
    helm uninstall jaeger -n "$NAMESPACE" 2>/dev/null || print_warning "Jaeger release not found"
    
    # Wait for pods to terminate
    print_status "Waiting for pods to terminate..."
    sleep 10
    
    # Force delete any remaining pods
    kubectl delete pods --all -n "$NAMESPACE" --force --grace-period=0 2>/dev/null || true
    
    # Delete PVCs (if any)
    print_status "Removing Persistent Volume Claims..."
    kubectl delete pvc --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete secrets (jaeger-specific)
    print_status "Removing Jaeger secrets..."
    kubectl delete secret jaeger-secret -n "$NAMESPACE" 2>/dev/null || true
    # Note: We keep elasticsearch-master-credentials and elasticsearch-master-certs
    # as they are shared resources needed for Elasticsearch connectivity
    
    # Delete configmaps
    print_status "Removing configmaps..."
    kubectl delete configmap --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete services
    print_status "Removing services..."
    kubectl delete svc --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete ingress
    print_status "Removing ingress..."
    kubectl delete ingress --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete ServiceMonitors (if any)
    print_status "Removing ServiceMonitors..."
    kubectl delete servicemonitor --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete namespace (optional - uncomment if you want to recreate it)
    # kubectl delete namespace "$NAMESPACE" 2>/dev/null || true
    
    print_success "Jaeger stack cleanup completed!"
}

# Function to setup prerequisites
setup_prerequisites() {
    print_status "🔧 Setting up prerequisites..."
    
    # Check required commands
    check_command kubectl
    check_command helm
    
    # Check if we can connect to the cluster
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    print_status "Connected to Kubernetes cluster"
    
    # Add Jaeger Helm repository
    print_status "Adding Jaeger Helm repository..."
    helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
    helm repo update
    
    # Create namespace if it doesn't exist
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        print_status "Creating namespace '$NAMESPACE'..."
        kubectl create namespace "$NAMESPACE"
    else
        print_status "Namespace '$NAMESPACE' already exists"
    fi
    
    print_success "Prerequisites setup completed!"
}

# Function to check Elasticsearch prerequisites
check_elasticsearch_prerequisites() {
    print_status "🔍 Checking Elasticsearch prerequisites..."
    
    # Check if Elasticsearch is running in logging namespace
    if ! kubectl get pods -n logging -l app=elasticsearch-master &> /dev/null; then
        print_error "Elasticsearch not found in 'logging' namespace."
        print_error "Please install ELK stack first using: ./scripts/setup-elk.sh install"
        exit 1
    fi
    
    # Check if Elasticsearch is ready
    if ! kubectl get pods -n logging -l app=elasticsearch-master -o jsonpath='{.items[0].status.phase}' | grep -q "Running"; then
        print_error "Elasticsearch is not running. Please check ELK stack status."
        exit 1
    fi
    
    # Check if Elasticsearch credentials exist
    if ! kubectl get secret elasticsearch-master-credentials -n logging &> /dev/null; then
        print_error "Elasticsearch credentials not found in 'logging' namespace."
        print_error "Please ensure ELK stack is properly installed."
        exit 1
    fi
    
    print_success "Elasticsearch prerequisites verified!"
}

# Function to copy Elasticsearch credentials and certificates
copy_elasticsearch_credentials() {
    print_status "📋 Copying Elasticsearch credentials and certificates to tracing namespace..."
    
    # Check if Elasticsearch credentials exist in logging namespace
    if ! kubectl get secret elasticsearch-master-credentials -n logging &> /dev/null; then
        print_error "Could not find Elasticsearch credentials in logging namespace"
        exit 1
    fi
    
    # Check if Elasticsearch certificates exist in logging namespace
    if ! kubectl get secret elasticsearch-master-certs -n logging &> /dev/null; then
        print_error "Could not find Elasticsearch certificates in logging namespace"
        exit 1
    fi
    
    # Copy Elasticsearch credentials
    print_status "Copying Elasticsearch credentials..."
    if kubectl get secret elasticsearch-master-credentials -n tracing &> /dev/null; then
        print_status "Elasticsearch credentials already exist in tracing namespace"
        
        # Delete existing secret to avoid conflicts
        print_status "Removing existing credentials to update them..."
        kubectl delete secret elasticsearch-master-credentials -n tracing
    fi
    
    # Copy Elasticsearch credentials from logging to tracing namespace
    # Remove resourceVersion, uid, and creationTimestamp from the secret
    # :d is a delimiter
    kubectl get secret elasticsearch-master-credentials -n logging -o yaml | \
        sed 's/namespace: logging/namespace: tracing/' | \
        sed '/resourceVersion:/d' | \
        sed '/uid:/d' | \
        sed '/creationTimestamp:/d' | \
        kubectl apply -f -
    
    # Copy Elasticsearch certificates
    print_status "Copying Elasticsearch certificates..."
    if kubectl get secret elasticsearch-master-certs -n tracing &> /dev/null; then
        print_status "Elasticsearch certificates already exist in tracing namespace"
        print_status "Removing existing certificates to update them..."
        kubectl delete secret elasticsearch-master-certs -n tracing
    fi
    
    kubectl get secret elasticsearch-master-certs -n logging -o yaml | \
        sed 's/namespace: logging/namespace: tracing/' | \
        sed '/resourceVersion:/d' | \
        sed '/uid:/d' | \
        sed '/creationTimestamp:/d' | \
        kubectl apply -f -
    
    print_success "Elasticsearch credentials and certificates copied successfully!"
}

# Function to install Jaeger
install_jaeger() {
    print_status "🔍 Installing Jaeger with Elasticsearch storage..."
    
    local values_file="$PROJECT_ROOT/helm-charts/jaeger/values.yaml"
    
    if [[ ! -f "$values_file" ]]; then
        print_error "Jaeger values file not found: $values_file"
        exit 1
    fi
    
    # Install Jaeger
    helm upgrade --install jaeger jaegertracing/jaeger \
        -n "$NAMESPACE" \
        -f "$values_file" \
        --timeout "$HELM_TIMEOUT" \
        --wait
    
    # Wait for Jaeger to be ready
    wait_for_pods "$NAMESPACE" "app.kubernetes.io/instance=jaeger" 600
    
    print_success "Jaeger installed successfully!"
}

# Function to verify installation
verify_installation() {
    print_status "🔍 Verifying Jaeger installation..."
    
    # Check pods
    print_status "Checking pod status..."
    kubectl get pods -n "$NAMESPACE"
    
    # Check services
    print_status "Checking services..."
    kubectl get svc -n "$NAMESPACE"
    
    # Check ingress
    print_status "Checking ingress..."
    kubectl get ingress -n "$NAMESPACE"
    
    # Test Jaeger Collector connection
    print_status "Testing Jaeger Collector connection..."
    
    # Port forward to Jaeger all-in-one metrics endpoint (port 14269 on the pod)
    kubectl port-forward -n "$NAMESPACE" deployment/jaeger 14269:14269 &
    local pf_pid=$!
    sleep 5
    
    # Test metrics endpoint
    if curl -s "http://localhost:14269/metrics" | grep -q "jaeger"; then
        print_success "Jaeger metrics endpoint is accessible!"
    else
        print_warning "Could not connect to Jaeger metrics endpoint"
    fi
    
    # Kill port forward
    kill $pf_pid 2>/dev/null || true
    
    # Test Jaeger Query UI
    print_status "Testing Jaeger Query UI..."
    
    # Get Jaeger UI URL
    local jaeger_host=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[0].spec.rules[0].host}' 2>/dev/null || echo "")
    
    if [ -n "$jaeger_host" ]; then
        print_success "Jaeger UI available at: http://$jaeger_host"
        
        # Test if UI is accessible
        if curl -s "http://$jaeger_host/api/services" &> /dev/null; then
            print_success "Jaeger UI is accessible!"
        else
            print_warning "Jaeger UI might not be ready yet. Please wait a few minutes."
        fi
    else
        print_warning "Jaeger ingress not found. You can access Jaeger UI via port-forward:"
        echo "kubectl port-forward -n $NAMESPACE svc/jaeger-query 16686:16686"
        echo "Then access: http://localhost:16686"
    fi
    
    # Test Elasticsearch connectivity from Jaeger
    print_status "Testing Elasticsearch connectivity from Jaeger..."
    
    # Check if Jaeger pod can resolve Elasticsearch service
    #nslookup is a command that resolves a domain name to an IP address
    #it is used to check if the Jaeger pod can resolve the Elasticsearch service
    if kubectl exec -n "$NAMESPACE" deployment/jaeger -- \
        nslookup elasticsearch-master.logging.svc.cluster.local &> /dev/null; then
        print_success "Jaeger can resolve Elasticsearch service!"
        
        # Check Jaeger logs for Elasticsearch connection status
        if kubectl logs -n "$NAMESPACE" deployment/jaeger --tail=100 | grep -qi "elasticsearch.*detected\|elasticsearch.*connected\|elasticsearch.*ready\|storage.*ready"; then
            print_success "Jaeger is connected to Elasticsearch storage!"
        else
            print_warning "Could not verify Elasticsearch connection from logs"
        fi
    else
        print_warning "Could not verify Elasticsearch connectivity from Jaeger"
    fi
    
    # Check Jaeger indices in Elasticsearch
    print_status "Checking Jaeger indices in Elasticsearch..."
    
    # Port forward to Elasticsearch
    kubectl port-forward -n logging svc/elasticsearch-master 9200:9200 &
    local es_pf_pid=$!
    sleep 5
    
    # Get Elasticsearch credentials
    local username=$(kubectl get secret elasticsearch-master-credentials -n logging -o jsonpath='{.data.username}' | base64 --decode)
    local password=$(kubectl get secret elasticsearch-master-credentials -n logging -o jsonpath='{.data.password}' | base64 --decode)
    
    # Check for Jaeger indices
    if curl -s -u "$username:$password" "http://localhost:9200/_cat/indices/jaeger*" | grep -q "jaeger"; then
        print_success "Jaeger indices found in Elasticsearch!"
        curl -s -u "$username:$password" "http://localhost:9200/_cat/indices/jaeger*?v"
    else
        print_warning "No Jaeger indices found yet. They will be created when traces are received."
    fi
    
    # Kill Elasticsearch port forward
    kill $es_pf_pid 2>/dev/null || true
    
    print_success "Jaeger verification completed!"
}

# Function to show connection information
show_connection_info() {
    print_status "📊 Jaeger Connection Information:"
    echo ""
    echo "Application Configuration:"
    echo "  ENABLE_TRACING=true"
    echo "  OTEL_SERVICE_NAME=hand-gesture-api"
    echo "  JAEGER_COLLECTOR_HOST=jaeger-collector.tracing.svc.cluster.local"
    echo "  JAEGER_COLLECTOR_PORT=4317"
    echo ""
    echo "Jaeger Endpoints:"
    echo "  Collector (OTLP gRPC): jaeger-collector.tracing.svc.cluster.local:4317"
    echo "  Collector (HTTP): jaeger-collector.tracing.svc.cluster.local:14268"
    echo "  Query UI: jaeger-query.tracing.svc.cluster.local:16686"
    echo ""
    
    # Get Jaeger UI URL
    local jaeger_host=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[0].spec.rules[0].host}' 2>/dev/null || echo "")
    
    if [ -n "$jaeger_host" ]; then
        echo "External Access:"
        echo "  Jaeger UI: http://$jaeger_host"
    else
        echo "Port Forward Access:"
        echo "  kubectl port-forward -n $NAMESPACE svc/jaeger-query 16686:16686"
        echo "  Then access: http://localhost:16686"
    fi
    
    echo ""
    echo "Next Steps:"
    echo "1. Deploy your application with tracing enabled:"
    echo "   helm upgrade --install hand-gesture ./helm-charts/asl -n model-serving"
    echo ""
    echo "2. Generate some traffic to your application:"
    echo "   curl http://asl.34.63.222.25.nip.io/api/health"
    echo ""
    echo "3. View traces in Jaeger UI"
    echo ""
    echo "4. Check application logs for tracing status:"
    echo "   kubectl logs -n model-serving deployment/hand-gesture-deployment"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  cleanup     Clean up existing Jaeger stack resources"
    echo "  install     Install Jaeger stack with Elasticsearch storage"
    echo "  reinstall   Clean up and reinstall Jaeger stack"
    echo "  verify      Verify Jaeger stack installation"
    echo "  info        Show connection information"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 cleanup                    # Clean up existing resources"
    echo "  $0 install                    # Install Jaeger stack"
    echo "  $0 reinstall                  # Clean up and reinstall"
    echo "  $0 verify                     # Verify installation"
    echo "  $0 info                       # Show connection info"
    echo ""
    echo "Prerequisites:"
    echo "  - ELK stack must be installed and running"
    echo "  - Elasticsearch must be accessible in 'logging' namespace"
    echo "  - kubectl and helm must be installed"
}

# Main script logic
main() {
    case "${1:-}" in
        cleanup)
            cleanup_jaeger
            ;;
        install)
            setup_prerequisites
            check_elasticsearch_prerequisites
            copy_elasticsearch_credentials
            install_jaeger
            verify_installation
            show_connection_info
            ;;
        reinstall)
            cleanup_jaeger
            sleep 5
            setup_prerequisites
            check_elasticsearch_prerequisites
            copy_elasticsearch_credentials
            install_jaeger
            verify_installation
            show_connection_info
            ;;
        verify)
            verify_installation
            ;;
        info)
            show_connection_info
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            print_error "Invalid option: ${1:-}"
            echo ""
            show_usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"

# Usage examples:
# ./scripts/setup-jaeger.sh install
# ./scripts/setup-jaeger.sh reinstall
# ./scripts/setup-jaeger.sh verify
# ./scripts/setup-jaeger.sh cleanup
# ./scripts/setup-jaeger.sh info
# ./scripts/setup-jaeger.sh help 