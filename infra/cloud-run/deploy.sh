#!/usr/bin/env bash
set -euo pipefail

# KISANAI C2C Cloud Run Deployment Script
PROJECT_ID="${1:-project-52e7ca23-228b-4cfd-879}"
REGION="${2:-asia-south1}"
SERVICE_NAME="kisanai-c2c"

# Expert access code: from the environment, or .env.local (never committed).
if [ -z "${EXPERT_ACCESS_TOKEN:-}" ] && [ -f ".env.local" ]; then
  EXPERT_ACCESS_TOKEN=$(grep -E "^EXPERT_ACCESS_TOKEN=" .env.local | head -n1 | cut -d '=' -f2- | tr -d '"'"'"'\r' || true)
fi
if [ -z "${EXPERT_ACCESS_TOKEN:-}" ]; then
  echo "Set EXPERT_ACCESS_TOKEN (the code officers use to open the expert workspace)." >&2
  exit 1
fi
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")

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
  --max-instances=1 \
  --timeout=60 \
  --set-env-vars="^@^APP_ENV=development@NODE_ID=india-node-mh@NODE_LABEL=KISANAI India node@NODE_SUBDIVISIONS=IN-MH,IN-PB,IN-UP@PUBLIC_BASE_URL=https://${SERVICE_NAME}-${PROJECT_NUMBER}.${REGION}.run.app@EXPERT_ACCESS_TOKEN=${EXPERT_ACCESS_TOKEN}@STORE_PROVIDER=sqlite@SQLITE_PATH=/tmp/kisanai.sqlite3@MEDIA_PROVIDER=local@MEDIA_DIRECTORY=/tmp/media@AI_ENABLED=true@AI_PROVIDER=vertex@GEMINI_MODEL=gemini-3.5-flash@GEMINI_FALLBACK_MODEL=gemini-3.7-flash@VERTEX_LOCATION=${REGION}@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}@EARTH_ENGINE_ENABLED=true@SPEECH_ENABLED=true@OPEN_METEO_ENABLED=true@IMD_ENABLED=true"

echo "Deployment finished."
