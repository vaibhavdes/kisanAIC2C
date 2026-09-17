#!/usr/bin/env bash
set -euo pipefail

# KISANAI C2C Cloud Run Deployment Script
PROJECT_ID="${1:-project-52e7ca23-228b-4cfd-879}"
REGION="${2:-asia-south1}"
SERVICE_NAME="kisanai-c2c"

echo "Deploying ${SERVICE_NAME} to Google Cloud Run..."
echo "Project: ${PROJECT_ID}"
echo "Region:  ${REGION}"

# Build and deploy from source via the root Dockerfile
gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --source="." \
  --allow-unauthenticated \
  --port=8080 \
  --memory=1Gi \
  --cpu=1 \
  --concurrency=80 \
  --min-instances=0 \
  --max-instances=1 \
  --timeout=60 \
  --set-env-vars="APP_ENV=development,NODE_ID=india-node-mh,AUTH_MODE=local,STORE_PROVIDER=sqlite,SQLITE_PATH=/tmp/kisanai.sqlite3,MEDIA_PROVIDER=local,MEDIA_DIRECTORY=/tmp/media,AI_ENABLED=true,AI_PROVIDER=vertex,GEMINI_MODEL=gemini-2.5-flash,VERTEX_LOCATION=${REGION},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},EARTH_ENGINE_ENABLED=true,SPEECH_ENABLED=true,GOOGLE_MAPS_API_KEY=AIzaSyAsrgbdtP_BJV8QYayrH3ZpHi13aTaQq-g,OPEN_METEO_ENABLED=true,IMD_ENABLED=true"

echo "Deployment finished."
