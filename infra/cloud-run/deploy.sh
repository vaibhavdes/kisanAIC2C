#!/usr/bin/env bash
set -euo pipefail

# Deploys KISANAI to Cloud Run from source (root Dockerfile).
# IMD stays off until IMD API credentials are added (IMD_EMAIL, IMD_PASSWORD, IMD_API_KEY).
# Farms, soil tests and advice are stored in Firestore (database kisanai-ag02) and uploaded
# photos in Cloud Storage, so data survives new revisions and the service can scale out.
# The expert review code comes from Secret Manager (secret kisanai-ag02-expert-code).
PROJECT_ID="${1:-project-52e7ca23-228b-4cfd-879}"
REGION="${2:-asia-south1}"
SERVICE_NAME="kisanai-c2c"
FIRESTORE_DATABASE="kisanai-ag02"
MEDIA_BUCKET="${PROJECT_ID}-kisanai-ag02"

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
  --min-instances=1 \
  --max-instances=3 \
  --session-affinity \
  --timeout=60 \
  --set-secrets="EXPERT_ACCESS_CODE=kisanai-ag02-expert-code:latest" \
  --set-env-vars="APP_ENV=development,NODE_ID=india-node-mh,AUTH_MODE=local,STORE_PROVIDER=firestore,FIRESTORE_DATABASE=${FIRESTORE_DATABASE},MEDIA_PROVIDER=gcs,MEDIA_BUCKET=${MEDIA_BUCKET},AI_ENABLED=true,AI_PROVIDER=vertex,GEMINI_MODEL=gemini-2.5-flash,VERTEX_LOCATION=${REGION},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},EARTH_ENGINE_ENABLED=true,SPEECH_ENABLED=true,OPEN_METEO_ENABLED=true,IMD_ENABLED=false"

echo "Deployment finished."
