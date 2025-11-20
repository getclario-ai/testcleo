#!/bin/bash

# GCP Deployment Script for Legacy Data Manager
# Deploys backend and frontend to Google Cloud Run
#
# Usage:
#   ./deploy-to-gcp.sh              # Deploy both backend and frontend
#   ./deploy-to-gcp.sh --backend-only   # Deploy only backend
#   ./deploy-to-gcp.sh --frontend-only  # Deploy only frontend

set -e  # Exit on error

# Configuration
PROJECT_ID="c-stg-2"
PROJECT_NUMBER="1003880222498"
REGION="us-central1"
BACKEND_SERVICE="legacy-data-api"
FRONTEND_SERVICE="legacy-data-frontend"
DB_INSTANCE="c-stg-2:us-central1:clario-stg-db"
DB_PASSWORD='Q]8xa~6"15l<Hh=t'  # Should be from Secret Manager or secure input

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if gcloud is installed and authenticated
check_gcloud_login() {
    if ! command -v gcloud &> /dev/null; then
        print_error "gcloud CLI is not installed. Please install it first."
        exit 1
    fi
    
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        print_error "Not authenticated with gcloud. Please run: gcloud auth login"
        exit 1
    fi
    
    print_info "gcloud authentication verified"
}

# Deploy backend
deploy_backend() {
    print_info "Deploying backend to Cloud Run..."
    
    cd backend
    
    # Build and push Docker image
    print_info "Building Docker image..."
    gcloud builds submit \
        --tag us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/$BACKEND_SERVICE:latest \
        --project=$PROJECT_ID \
        --quiet
    
    # Deploy to Cloud Run
    print_info "Deploying to Cloud Run..."
    gcloud run deploy $BACKEND_SERVICE \
        --image us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/$BACKEND_SERVICE:latest \
        --region $REGION \
        --platform managed \
        --allow-unauthenticated \
        --add-cloudsql-instances $DB_INSTANCE \
        --set-env-vars "DATABASE_URL=postgresql://postgres:$DB_PASSWORD@/clario_stg?host=/cloudsql/$DB_INSTANCE,FRONTEND_URL=https://$FRONTEND_SERVICE-$PROJECT_NUMBER.$REGION.run.app,GOOGLE_REDIRECT_URI=https://$BACKEND_SERVICE-$PROJECT_NUMBER.$REGION.run.app/api/v1/auth/google/callback" \
        --set-secrets "GOOGLE_CLIENT_ID=google-client-id:latest,GOOGLE_CLIENT_SECRET=google-client-secret:latest,SLACK_SIGNING_SECRET=slack-signing-secret:latest,SLACK_BOT_TOKEN=slack-bot-token:latest" \
        --project=$PROJECT_ID \
        --quiet
    
    cd ..
    
    print_info "Backend deployed successfully!"
    print_info "Backend URL: https://$BACKEND_SERVICE-$PROJECT_NUMBER.$REGION.run.app"
}

# Deploy frontend
deploy_frontend() {
    print_info "Deploying frontend to Cloud Run..."
    
    # Build and push Docker image with API URL
    # Note: cloudbuild.yaml expects to run from legacy-data-manager root
    print_info "Building Docker image with API URL..."
    gcloud builds submit \
        --config=frontend/cloudbuild.yaml \
        --substitutions=_API_BASE_URL=https://$BACKEND_SERVICE-$PROJECT_NUMBER.$REGION.run.app \
        --project=$PROJECT_ID \
        --quiet
    
    # Deploy to Cloud Run
    print_info "Deploying to Cloud Run..."
    gcloud run deploy $FRONTEND_SERVICE \
        --image us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/$FRONTEND_SERVICE:latest \
        --region $REGION \
        --platform managed \
        --allow-unauthenticated \
        --project=$PROJECT_ID \
        --quiet
    
    print_info "Frontend deployed successfully!"
    print_info "Frontend URL: https://$FRONTEND_SERVICE-$PROJECT_NUMBER.$REGION.run.app"
}

# Main execution
main() {
    print_info "Starting GCP deployment..."
    print_info "Project: $PROJECT_ID"
    print_info "Region: $REGION"
    
    check_gcloud_login
    
    # Parse arguments
    if [ "$1" == "--backend-only" ]; then
        deploy_backend
    elif [ "$1" == "--frontend-only" ]; then
        deploy_frontend
    else
        # Deploy both
        deploy_backend
        deploy_frontend
    fi
    
    print_info "Deployment complete!"
    print_info "Frontend: https://$FRONTEND_SERVICE-$PROJECT_NUMBER.$REGION.run.app"
    print_info "Backend: https://$BACKEND_SERVICE-$PROJECT_NUMBER.$REGION.run.app"
}

# Run main function
main "$@"

