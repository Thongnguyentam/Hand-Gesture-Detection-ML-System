#!/bin/bash

# ELK Stack Setup Script
# This script can clean up existing ELK resources and reinstall the entire stack

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="logging"
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
# If the command does NOT exist, suppress all output (stdout and stderr) using &> /dev/null.
# Example: check_command kubectl
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

# Function to clean up ELK stack
cleanup_elk() {
    print_status "🧹 Cleaning up existing ELK stack..."
    
    # Remove Helm releases
    print_status "Removing Helm releases..."
    helm uninstall filebeat -n "$NAMESPACE" 2>/dev/null || print_warning "Filebeat release not found"
    helm uninstall logstash -n "$NAMESPACE" 2>/dev/null || print_warning "Logstash release not found" 
    helm uninstall kibana -n "$NAMESPACE" 2>/dev/null || print_warning "Kibana release not found"
    helm uninstall elasticsearch -n "$NAMESPACE" 2>/dev/null || print_warning "Elasticsearch release not found"
    
    # Wait for pods to terminate
    print_status "Waiting for pods to terminate..."
    sleep 10
    
    # Force delete any remaining pods
    kubectl delete pods --all -n "$NAMESPACE" --force --grace-period=0 2>/dev/null || true
    
    # Delete PVCs (this will delete all data!)
    print_status "Removing Persistent Volume Claims..."
    kubectl delete pvc --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete secrets (optional - comment out if you want to keep them)
    print_status "Removing secrets..."
    kubectl delete secret elasticsearch-master-credentials -n "$NAMESPACE" 2>/dev/null || true
    kubectl delete secret elasticsearch-master-certs -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete configmaps
    print_status "Removing configmaps..."
    kubectl delete configmap --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete services
    print_status "Removing services..."
    kubectl delete svc --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete ingress
    print_status "Removing ingress..."
    kubectl delete ingress --all -n "$NAMESPACE" 2>/dev/null || true
    
    # Delete namespace (optional - uncomment if you want to recreate it)
    # kubectl delete namespace "$NAMESPACE" 2>/dev/null || true
    
    print_success "ELK stack cleanup completed!"
}

# Function to setup prerequisites
setup_prerequisites() {
    print_status "🔧 Setting up prerequisites..."
    
    # Check required commands
    check_command kubectl
    check_command helm
    
    # Add Elastic Helm repository
    print_status "Adding Elastic Helm repository..."
    helm repo add elastic https://helm.elastic.co
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

# Function to install Elasticsearch
install_elasticsearch() {
    print_status "📊 Installing Elasticsearch..."
    
    local values_file="$PROJECT_ROOT/helm-charts/elk/elasticsearch/values.yml"
    
    if [[ ! -f "$values_file" ]]; then
        print_error "Elasticsearch values file not found: $values_file"
        exit 1
    fi
    
    helm upgrade --install elasticsearch elastic/elasticsearch \
        -n "$NAMESPACE" \
        -f "$values_file" \
        --timeout "$HELM_TIMEOUT" \
        --wait
    
    # Wait for Elasticsearch to be ready
    wait_for_pods "$NAMESPACE" "app=elasticsearch-master" 600
    
    # Get credentials
    print_status "Retrieving Elasticsearch credentials..."
    sleep 10  # Wait for secret to be created
    
    if kubectl get secret elasticsearch-master-credentials -n "$NAMESPACE" &> /dev/null; then
        local username=$(kubectl get secret elasticsearch-master-credentials -n "$NAMESPACE" -o jsonpath='{.data.username}' | base64 --decode)
        local password=$(kubectl get secret elasticsearch-master-credentials -n "$NAMESPACE" -o jsonpath='{.data.password}' | base64 --decode)
        
        print_success "Elasticsearch installed successfully!"
        print_status "Username: $username"
        print_status "Password: $password"
        
        # Save credentials to file
        echo "ELASTICSEARCH_USERNAME=$username" > "$PROJECT_ROOT/.env.elasticsearch"
        echo "ELASTICSEARCH_PASSWORD=$password" >> "$PROJECT_ROOT/.env.elasticsearch"
        print_status "Credentials saved to .env.elasticsearch"
    else
        print_warning "Could not retrieve Elasticsearch credentials"
    fi
}

# Function to install Kibana
install_kibana() {
    print_status "📈 Installing Kibana..."
    
    local values_file="$PROJECT_ROOT/helm-charts/elk/kibana/values.yml"
    
    if [[ ! -f "$values_file" ]]; then
        print_error "Kibana values file not found: $values_file"
        exit 1
    fi
    
    helm upgrade --install kibana elastic/kibana \
        -n "$NAMESPACE" \
        -f "$values_file" \
        --timeout "$HELM_TIMEOUT" \
        --wait
    
    # Wait for Kibana to be ready
    wait_for_pods "$NAMESPACE" "app=kibana" 300
    
    print_success "Kibana installed successfully!"
    print_status "Access Kibana at: http://kibana.34.63.222.25.nip.io"
}

# Function to install Logstash
install_logstash() {
    print_status "🔄 Installing Logstash..."
    
    local values_file="$PROJECT_ROOT/helm-charts/elk/logstash/values.yml"
    
    if [[ ! -f "$values_file" ]]; then
        print_error "Logstash values file not found: $values_file"
        exit 1
    fi
    
    helm upgrade --install logstash elastic/logstash \
        -n "$NAMESPACE" \
        -f "$values_file" \
        --timeout "$HELM_TIMEOUT" \
        --wait
    
    # Wait for Logstash to be ready
    wait_for_pods "$NAMESPACE" "app=logstash-logstash" 300
    
    print_success "Logstash installed successfully!"
}

# Function to install Filebeat
install_filebeat() {
    print_status "📋 Installing Filebeat..."
    
    local values_file="$PROJECT_ROOT/helm-charts/elk/filebeat/values.yml"
    
    if [[ ! -f "$values_file" ]]; then
        print_error "Filebeat values file not found: $values_file"
        exit 1
    fi
    
    helm upgrade --install filebeat elastic/filebeat \
        -n "$NAMESPACE" \
        -f "$values_file" \
        --timeout "$HELM_TIMEOUT" \
        --wait
    
    # Wait for Filebeat to be ready
    wait_for_pods "$NAMESPACE" "app=filebeat-filebeat" 300
    
    print_success "Filebeat installed successfully!"
}

# Function to verify installation
verify_installation() {
    print_status "🔍 Verifying ELK stack installation..."
    
    # Check pods
    print_status "Checking pod status..."
    kubectl get pods -n "$NAMESPACE"
    
    # Check services
    print_status "Checking services..."
    kubectl get svc -n "$NAMESPACE"
    
    # Check ingress
    print_status "Checking ingress..."
    kubectl get ingress -n "$NAMESPACE"
    
    # Test Elasticsearch connection
    print_status "Testing Elasticsearch connection..."
    if kubectl get secret elasticsearch-master-credentials -n "$NAMESPACE" &> /dev/null; then
        local username=$(kubectl get secret elasticsearch-master-credentials -n "$NAMESPACE" -o jsonpath='{.data.username}' | base64 --decode)
        local password=$(kubectl get secret elasticsearch-master-credentials -n "$NAMESPACE" -o jsonpath='{.data.password}' | base64 --decode)
        
        # Port forward in background
        kubectl port-forward svc/elasticsearch-master -n "$NAMESPACE" 9200:9200 &
        local pf_pid=$! # $! is the process ID of the last background process
        sleep 5
        
        # Test connection
        if curl -k -u "$username:$password" "https://localhost:9200/_cluster/health" &> /dev/null; then
            print_success "Elasticsearch is accessible!"
        else
            print_warning "Could not connect to Elasticsearch"
        fi
        
        # Kill port forward
        kill $pf_pid 2>/dev/null || true
    fi
    
    print_success "ELK stack verification completed!"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  cleanup     Clean up existing ELK stack resources"
    echo "  install     Install ELK stack (Elasticsearch, Kibana, Logstash, Filebeat)"
    echo "  reinstall   Clean up and reinstall ELK stack"
    echo "  verify      Verify ELK stack installation"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 cleanup                    # Clean up existing resources"
    echo "  $0 install                    # Install ELK stack"
    echo "  $0 reinstall                  # Clean up and reinstall"
    echo "  $0 verify                     # Verify installation"
}

# Main script logic
main() {
    case "${1:-}" in # checks the first argument ($1) passed to the script.
        cleanup)
            cleanup_elk
            ;;
        install)
            setup_prerequisites
            install_elasticsearch
            install_kibana
            install_logstash
            install_filebeat
            verify_installation
            ;;
        reinstall)
            cleanup_elk
            sleep 5
            setup_prerequisites
            install_elasticsearch
            install_kibana
            install_logstash
            install_filebeat
            verify_installation
            ;;
        verify)
            verify_installation
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

# ./scripts/setup-elk.sh install
# ./scripts/setup-elk.sh reinstall
# ./scripts/setup-elk.sh verify
# ./scripts/setup-elk.sh cleanup
# ./scripts/setup-elk.sh help