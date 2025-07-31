#!/bin/bash

# Prometheus Stack Setup Script
# This script can clean up existing Prometheus resources and reinstall the entire stack

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="monitoring"
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

# Function to clean up Prometheus stack
cleanup_prometheus() {
    print_status "🧹 Cleaning up existing Prometheus stack..."
    
    # Remove Helm release
    print_status "Removing Helm release..."
    helm uninstall prometheus -n "$NAMESPACE" 2>/dev/null || print_warning "Prometheus stack release not found"
    
    # Wait for pods to terminate
    print_status "Waiting for pods to terminate..."
    sleep 10
    
    # Force delete any remaining pods
    kubectl delete pods --all -n "$NAMESPACE" --force --grace-period=0 2>/dev/null || true
    
    # Delete PVCs (this will delete all monitoring data!)
    print_status "Removing Persistent Volume Claims..."
    kubectl delete pvc --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete secrets
    print_status "Removing secrets..."
    kubectl delete secret --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete configmaps
    print_status "Removing configmaps..."
    kubectl delete configmap --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete services
    print_status "Removing services..."
    kubectl delete svc --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete ingress
    print_status "Removing ingress..."
    kubectl delete ingress --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete ServiceMonitors and PrometheusRules
    print_status "Removing ServiceMonitors and PrometheusRules..."
    kubectl delete servicemonitor --all -n "$NAMESPACE" 2>/dev/null || true
    kubectl delete prometheusrule --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete CRDs (optional - uncomment if you want to remove CRDs)
    # print_status "Removing Prometheus Operator CRDs..."
    # kubectl delete crd prometheuses.monitoring.coreos.com 2>/dev/null || true
    # kubectl delete crd prometheusrules.monitoring.coreos.com 2>/dev/null || true
    # kubectl delete crd servicemonitors.monitoring.coreos.com 2>/dev/null || true
    # kubectl delete crd alertmanagers.monitoring.coreos.com 2>/dev/null || true
    
    print_success "Prometheus stack cleanup completed!"
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
    
    # Add Prometheus Community Helm repository
    print_status "Adding Prometheus Community Helm repository..."
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
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

# Function to install Prometheus stack
install_prometheus_stack() {
    print_status "📊 Installing Prometheus stack (Prometheus, Grafana, Alertmanager)..."
    
    local values_file="$PROJECT_ROOT/helm-charts/prometheus/values.yml"
    
    if [[ ! -f "$values_file" ]]; then
        print_error "Prometheus values file not found: $values_file"
        exit 1
    fi
    
    # Install kube-prometheus-stack
    helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
        -n "$NAMESPACE" \
        -f "$values_file" \
        --timeout "$HELM_TIMEOUT" \
        --wait
    
    # Wait for core components to be ready
    wait_for_pods "$NAMESPACE" "app.kubernetes.io/name=prometheus" 600
    wait_for_pods "$NAMESPACE" "app.kubernetes.io/name=grafana" 300
    wait_for_pods "$NAMESPACE" "app.kubernetes.io/name=alertmanager" 300
    
    print_success "Prometheus stack installed successfully!"
}

# Function to get access credentials
get_credentials() {
    print_status "🔑 Retrieving access credentials..."
    
    # Get Grafana admin password
    if kubectl get secret prometheus-grafana -n "$NAMESPACE" &> /dev/null; then
        local grafana_password=$(kubectl get secret prometheus-grafana -n "$NAMESPACE" -o jsonpath='{.data.admin-password}' | base64 --decode)
        
        print_success "Grafana credentials retrieved!"
        print_status "Username: admin"
        print_status "Password: $grafana_password"
        
        # Save credentials to file
        echo "GRAFANA_USERNAME=admin" > "$PROJECT_ROOT/.env.grafana"
        echo "GRAFANA_PASSWORD=$grafana_password" >> "$PROJECT_ROOT/.env.grafana"
        print_status "Credentials saved to .env.grafana"
    else
        print_warning "Could not retrieve Grafana credentials"
    fi
}

# Function to verify installation
verify_installation() {
    print_status "🔍 Verifying Prometheus stack installation..."
    
    # Check pods
    print_status "Checking pod status..."
    kubectl get pods -n "$NAMESPACE"
    
    # Check services
    print_status "Checking services..."
    kubectl get svc -n "$NAMESPACE"
    
    # Check ingress
    print_status "Checking ingress..."
    kubectl get ingress -n "$NAMESPACE"
    
    # Check ServiceMonitors
    print_status "Checking ServiceMonitors..."
    kubectl get servicemonitor -n "$NAMESPACE"
    
    # Test Prometheus connection
    print_status "Testing Prometheus connection..."
    kubectl port-forward -n "$NAMESPACE" svc/prometheus-kube-prometheus-prometheus 9090:9090 &
    local prom_pf_pid=$!
    sleep 5
    
    if curl -s "http://localhost:9090/api/v1/query?query=up" | grep -q "success"; then
        print_success "Prometheus is accessible!"
    else
        print_warning "Could not connect to Prometheus"
    fi
    
    # Kill port forward
    kill $prom_pf_pid 2>/dev/null || true
    
    # Test Grafana connection
    print_status "Testing Grafana connection..."
    kubectl port-forward -n "$NAMESPACE" svc/prometheus-grafana 3000:80 &
    local grafana_pf_pid=$!
    sleep 5
    
    if curl -s "http://localhost:3000/api/health" | grep -q "ok"; then
        print_success "Grafana is accessible!"
    else
        print_warning "Could not connect to Grafana"
    fi
    
    # Kill port forward
    kill $grafana_pf_pid 2>/dev/null || true
    
    # Test Alertmanager connection
    print_status "Testing Alertmanager connection..."
    kubectl port-forward -n "$NAMESPACE" svc/prometheus-kube-prometheus-alertmanager 9093:9093 &
    local alert_pf_pid=$!
    sleep 5
    
    if curl -s "http://localhost:9093/api/v2/status" | grep -q "uptime"; then
        print_success "Alertmanager is accessible!"
    else
        print_warning "Could not connect to Alertmanager"
    fi
    
    # Kill port forward
    kill $alert_pf_pid 2>/dev/null || true
    
    # Check control plane monitoring
    print_status "Checking control plane monitoring targets..."
    kubectl port-forward -n "$NAMESPACE" svc/prometheus-kube-prometheus-prometheus 9090:9090 &
    local prom_pf_pid2=$!
    sleep 5
    
    # Check if control plane components are being scraped
    local control_plane_targets=("apiserver" "kubelet" "kube-controller-manager" "kube-scheduler" "kube-proxy" "etcd" "coredns")
    
    for target in "${control_plane_targets[@]}"; do
        if curl -s "http://localhost:9090/api/v1/targets" | grep -q "$target"; then
            print_success "✓ $target is being monitored"
        else
            print_warning "⚠ $target monitoring may not be configured"
        fi
    done
    
    # Kill port forward
    kill $prom_pf_pid2 2>/dev/null || true
    
    print_success "Prometheus stack verification completed!"
}

# Function to show connection information
show_connection_info() {
    print_status "📊 Prometheus Stack Connection Information:"
    echo ""
    echo "External Access URLs:"
    echo "  Grafana: http://grafana.34.63.222.25.nip.io"
    echo "  Prometheus: http://prometheus.34.63.222.25.nip.io"
    echo "  Alertmanager: http://alertmanager.34.63.222.25.nip.io"
    echo ""
    echo "Local Access (via port-forward):"
    echo "  Grafana: kubectl port-forward -n $NAMESPACE svc/prometheus-grafana 3000:80"
    echo "  Prometheus: kubectl port-forward -n $NAMESPACE svc/prometheus-kube-prometheus-prometheus 9090:9090"
    echo "  Alertmanager: kubectl port-forward -n $NAMESPACE svc/prometheus-kube-prometheus-alertmanager 9093:9093"
    echo ""
    
    # Get Grafana credentials
    if kubectl get secret prometheus-grafana -n "$NAMESPACE" &> /dev/null; then
        local grafana_password=$(kubectl get secret prometheus-grafana -n "$NAMESPACE" -o jsonpath='{.data.admin-password}' | base64 --decode)
        echo "Grafana Credentials:"
        echo "  Username: admin"
        echo "  Password: $grafana_password"
    fi
    
    echo ""
    echo "Monitoring Coverage:"
    echo "  ✓ Kubernetes Control Plane (API Server, Kubelet, Scheduler, etc.)"
    echo "  ✓ Node Metrics (CPU, Memory, Disk, Network)"
    echo "  ✓ Container Metrics (via cAdvisor)"
    echo "  ✓ Kubernetes Objects State (via Kube State Metrics)"
    echo "  ✓ Application Metrics (via ServiceMonitors)"
    echo ""
    echo "Next Steps:"
    echo "1. Access Grafana and explore pre-built dashboards"
    echo "2. Create ServiceMonitors for your applications:"
    echo "   kubectl apply -f your-app-servicemonitor.yaml"
    echo "3. Configure alerting rules in Prometheus"
    echo "4. Set up notification channels in Alertmanager"
    echo ""
    echo "Useful Commands:"
    echo "  Check ServiceMonitors: kubectl get servicemonitor -A"
    echo "  Check PrometheusRules: kubectl get prometheusrule -A"
    echo "  View Prometheus targets: kubectl port-forward -n $NAMESPACE svc/prometheus-kube-prometheus-prometheus 9090:9090"
    echo "  Then visit: http://localhost:9090/targets"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  cleanup     Clean up existing Prometheus stack resources"
    echo "  install     Install Prometheus stack (Prometheus, Grafana, Alertmanager)"
    echo "  reinstall   Clean up and reinstall Prometheus stack"
    echo "  verify      Verify Prometheus stack installation"
    echo "  info        Show connection information"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 cleanup                    # Clean up existing resources"
    echo "  $0 install                    # Install Prometheus stack"
    echo "  $0 reinstall                  # Clean up and reinstall"
    echo "  $0 verify                     # Verify installation"
    echo "  $0 info                       # Show connection info"
    echo ""
    echo "Prerequisites:"
    echo "  - Kubernetes cluster with NGINX Ingress Controller"
    echo "  - Helm 3.x installed"
    echo "  - kubectl configured for cluster access"
    echo "  - Sufficient cluster resources"
}

# Main script logic
main() {
    case "${1:-}" in
        cleanup)
            cleanup_prometheus
            ;;
        install)
            setup_prerequisites
            install_prometheus_stack
            get_credentials
            verify_installation
            show_connection_info
            ;;
        reinstall)
            cleanup_prometheus
            sleep 5
            setup_prerequisites
            install_prometheus_stack
            get_credentials
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
# ./scripts/setup-prometheus.sh install
# ./scripts/setup-prometheus.sh reinstall
# ./scripts/setup-prometheus.sh verify
# ./scripts/setup-prometheus.sh cleanup
# ./scripts/setup-prometheus.sh info
# ./scripts/setup-prometheus.sh help
