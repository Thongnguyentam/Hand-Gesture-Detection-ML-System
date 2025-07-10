# Hand Gesture Detection API

A real-time hand gesture recognition system featuring a Python OpenCV client and a FastAPI backend, deployed on Google Kubernetes Engine (GKE) via a fully automated CI/CD pipeline with Jenkins.

---

## Architecture Overview
<div align="center">
  <img src="images/asl_architecture.png" alt="Jaeger Architecture Overview" width="800">
  <p><em>Figure 1: Complete architecture for serving ASL hand gesture detection API</em></p>
</div>

This project is composed of several key components that work together to provide a seamless development and deployment experience:

-   **Webcam Client (`app.py`):** Captures video from a webcam, uses `mediapipe` to detect hand landmarks, and streams the data to the backend via WebSockets.
-   **API Backend (`main.py`):** A `FastAPI` application that receives landmark data, uses a pre-trained model to classify the hand gesture, and returns the prediction.
-   **CI/CD Pipeline (`Jenkinsfile`):** An automated Jenkins pipeline that tests the code, builds a Docker image, and deploys the application to Kubernetes.
-   **Infrastructure as Code (`iac/`):** Terraform scripts to provision the necessary cloud infrastructure on GCP, including the GKE cluster and the Jenkins VM.
-   **Kubernetes Deployment (`helm-charts/`):** A Helm chart that defines all the necessary Kubernetes resources for a scalable and secure deployment.
-   **Observability Stack:** Comprehensive monitoring, logging, and tracing setup using Prometheus, ELK Stack, and Jaeger for production-ready observability.

---

## Getting Started

### Core Setup Guides
-   **[1. Local Development & Testing Guide](docs/1.%20LOCAL_DEVELOPMENT.md)**: Instructions for running the services on a local machine and testing with Minikube.
-   **[2. Infrastructure Setup Guide](docs/2.%20INFRASTRUCTURE_SETUP.md)**: One-time setup for provisioning GCP resources with Terraform.
-   **[3. Jenkins Instance Setup Guide](docs/3.%20JENKINS_SETUP.md)**: One-time setup for configuring the Jenkins VM and its credentials.
-   **[4. Kubernetes Deployment Guide (Helm)](docs/4.%20HELM_AND_KUBERNETES.md)**: A detailed explanation of the Helm chart and Kubernetes resources.

### Observability & Operations
-   **[5. Logging with ELK Stack](docs/5.%20LOGGING_WITH_ELK_STACK.md)**: Complete guide for centralized logging using Elasticsearch, Filebeat, and Kibana.
-   **[6. Monitoring with Prometheus](docs/6.%20MONITORING_PROMETHEUS.md)**: Comprehensive monitoring setup using Prometheus, Grafana, and Alertmanager.
-   **[7. Distributed Tracing with Jaeger](docs/7.%20TRACING_WITH_JAEGER.md)**: Production-ready distributed tracing implementation for microservices observability.

---

## Project Structure

```
.
├── api/                  # FastAPI application source code
├── app.py                # OpenCV client application
├── docs/                 # Detailed setup and development guides
│   ├── 1. LOCAL_DEVELOPMENT.md
│   ├── 2. INFRASTRUCTURE_SETUP.md
│   ├── 3. JENKINS_SETUP.md
│   ├── 4. HELM_AND_KUBERNETES.md
│   ├── 5. LOGGING_WITH_ELK_STACK.md
│   ├── 6. MONITORING_PROMETHEUS.md
│   └── 7. TRACING_WITH_JAEGER.md
├── helm-charts/          # Helm charts for Kubernetes deployment
│   ├── asl/              # Main application chart
│   ├── prometheus/       # Monitoring stack configuration
│   ├── elk/              # Logging stack configuration
│   └── jaeger/           # Tracing stack configuration
├── iac/                  # Terraform files for GCP infrastructure
├── model/                # Pre-trained ML models
├── scripts/              # Setup and automation scripts
│   ├── setup-prometheus.sh
│   ├── setup-elk.sh
│   └── setup-jaeger.sh
├── Dockerfile            # Defines the container image for the API
├── Jenkinsfile           # Declarative CI/CD pipeline for Jenkins
├── main.py               # FastAPI application entry point
└── README.md             # This file
```

---

## Observability Stack

Our production deployment includes a comprehensive observability stack:

### Monitoring (Prometheus + Grafana)
- **Metrics Collection**: Prometheus scrapes metrics from applications and Kubernetes components
- **Visualization**: Grafana dashboards for real-time monitoring and alerting
- **Alerting**: Alertmanager for intelligent alert routing and grouping
- **Access**: `http://grafana.34.63.222.25.nip.io` and `http://prometheus.34.63.222.25.nip.io`

### Logging (ELK Stack)
- **Log Collection**: Filebeat collects logs from all pods and system components
- **Storage & Search**: Elasticsearch for scalable log storage and powerful search capabilities
- **Visualization**: Kibana for log analysis, dashboards, and troubleshooting
- **Access**: `http://kibana.34.63.222.25.nip.io`

### Distributed Tracing (Jaeger)
- **Request Tracing**: End-to-end request tracking across microservices
- **Performance Analysis**: Identify bottlenecks and optimize service interactions
- **Storage**: Elasticsearch backend for persistent trace storage
- **Access**: `http://jaeger.34.63.222.25.nip.io`

---

## CI/CD Pipeline

The `Jenkinsfile` defines an automated, multi-branch pipeline that handles the entire lifecycle of the application. For a full breakdown of the pipeline's logic and stages, see the main `Jenkinsfile`.

## Kubernetes Deployment (Helm)

The application is deployed using the Helm chart located in `helm-charts/asl`. For a detailed explanation of the chart and the Kubernetes resources it creates, please see the **[Kubernetes Deployment Guide](docs/4.%20HELM_AND_KUBERNETES.md)**.
