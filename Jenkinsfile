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
        // Coverage threshold
        COVERAGE_THRESHOLD = '80'
    }

    stages {
        // Run Test and Build on main branch, feature/initial-code branch, or PRs
        stage('Test') {
            when {
                anyOf {
                    branch 'main'
                    branch 'feature/initial-code'
                    changeRequest()
                }
            }
            steps {
                sh '''#!/bin/bash
                    set -e

                    echo 'Testing with coverage enforcement...'
                    curl -Ls https://astral.sh/uv/install.sh | bash
                    export PATH="$HOME/.local/bin:$PATH"

                    # Debug: Print env vars (masked sensitive values)
                    echo "Environment loaded. Testing connection..."
                        
                    uv sync --locked --no-cache
                    
                    echo "Running tests with coverage..."
                    uv run --no-cache pytest --cov=api --cov-report=term-missing --cov-report=xml --cov-config=pyproject.toml --cov-fail-under=${COVERAGE_THRESHOLD}
                    
                    echo "Coverage check passed! Proceeding with pipeline..."
                '''
            }
            post {
                failure {
                    echo "❌ Tests failed or coverage below ${COVERAGE_THRESHOLD}%. Pipeline stopped."
                }
                success {
                    echo "✅ Tests passed with coverage >= ${COVERAGE_THRESHOLD}%. Proceeding to build..."
                }
            }
        }

        stage('Build') {
            when { 
                allOf {
                    // Run Build on main branch, feature/initial-code branch, or PRs
                    anyOf {
                        branch 'main'
                        branch 'feature/initial-code'
                        changeRequest() // handle PRs
                    }
                    // Only proceed if Test stage was successful
                    expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
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

        // Deploy from main branch and feature/initial-code branch
        stage('Deploy') {
            when {
                allOf {
                    anyOf {
                        branch 'main'
                        branch 'feature/initial-code'
                        changeRequest()
                    }
                    // Only proceed if previous stages were successful
                    expression { currentBuild.result == null || currentBuild.result == 'SUCCESS' }
                }
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
    
    post {
        failure {
            echo "❌ Pipeline failed. Check the logs above for details."
        }
        success {
            echo "✅ Pipeline completed successfully!"
        }
        always {
            // Clean up workspace
            cleanWs()
        }
    }
}