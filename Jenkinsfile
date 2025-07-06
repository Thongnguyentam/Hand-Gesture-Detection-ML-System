pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '10', daysToKeepStr: '10'))
        timestamps() // add timestamps to the build logs
    }

    environment {
        // DockerHub repository where the image will be pushed.`
        registry = 'thongnguyen0101/hand-gesture-detection'
        // Credentials for DockerHub
        registry_credentials = 'dockerhub-credentials'
        GCP_PROJECT = 'fsds-461704'
        GCP_REGION  = 'us-central1'
        CLUSTER     = 'asl-cluster'
        NAMESPACE   = 'model-serving'
        CHART_PATH  = './helm-charts/asl'
        RELEASE     = 'hand-gesture'
        // Add environment variables directly here
        MONGODB_CONNECTION_URL = credentials('MONGODB_CONNECTION_URL')
        JWT_SECRET = credentials('JWT_SECRET')
        GITHUB_TOKEN = credentials('github_access_token')
    }

    stages {
        // Only run Test and Build on main branch or PRs
        stage('Test') {
            when {
                anyOf {
                    branch 'main'
                    changeRequest()
                }
            }
            steps {
                sh '''#!/bin/bash
                    set -e

                    echo 'Testing...'
                    curl -Ls https://astral.sh/uv/install.sh | bash
                    export PATH="$HOME/.local/bin:$PATH"

                    # Debug: Print env vars (masked sensitive values)
                    echo "Environment loaded. Testing connection..."
                        
                    uv sync --locked --no-cache
                    uv run --no-cache pytest
                '''
            }
        }

        stage('Build') {
            when { // Only run Build on main branch or PRs
                anyOf {
                    branch 'main'
                    changeRequest() // handle PRs
                }
            }
            steps {
                script {
                    echo 'Building...'
                    
                    // Build a clean image without any secrets
                    def dockerImage = docker.build(registry + ":$BUILD_NUMBER")
                    echo "Pushing image to DockerHub..."
                    docker.withRegistry('https://registry.hub.docker.com', registry_credentials) {
                        dockerImage.push()
                        dockerImage.push('latest')
                    }
                }
            }
        }

        // Only deploy from main branch
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                // Wrap the entire stage's logic in withCredentials to securely load the GCloud key
                withCredentials([file(credentialsId: 'gcloud-service-account-key', variable: 'GCLOUD_KEY')]) {
                    script {
                        def tempValuesFile = 'temp-values.yaml'
                        
                        // Use writeFile to create the temp file. This is more secure and avoids warnings.
                        def yamlContent = """
secrets:
  mongodbUrl: "${MONGODB_CONNECTION_URL}"
  jwtSecret: "${JWT_SECRET}"
  githubToken: "${GITHUB_TOKEN}"
"""
                        writeFile file: tempValuesFile, text: yamlContent

                        try {
                            // Pass the filename to the shell script via a temporary environment variable
                            withEnv(["HELM_VALUES_FILE=${tempValuesFile}"]) {
                                // Use single quotes for the shell script for security and correctness
                                sh '''#!/bin/bash
                                    set -e

                    echo "Authenticating with Google Cloud..."
                                    gcloud auth activate-service-account --key-file="$GCLOUD_KEY"

                    echo "Fetching GKE credentials..."
                                    gcloud container clusters get-credentials "$CLUSTER" --region="$GCP_REGION" --project="$GCP_PROJECT"

                    echo "Deploying with Helm..."
                                    helm upgrade "$RELEASE" "$CHART_PATH" \
                                        --install \
                                        --create-namespace \
                                        --namespace "$NAMESPACE" \
                                        -f "$HELM_VALUES_FILE"
                                '''
                            }
                        } finally {
                            // Clean up the temporary values file
                            sh "rm -f ${tempValuesFile}"
                        }
                    }
                }
            }
        }
    }
}