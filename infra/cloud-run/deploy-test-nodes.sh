#!/usr/bin/env bash
set -euo pipefail

# Deploys two peer KISANAI nodes to separate Cloud Run services for testing the state network:
#   kisanai-c2c-test  - Maharashtra + Uttar Pradesh node
#   kisanai-node-pb   - Punjab node
# The production service (kisanai-c2c) is never touched by this script.
#
# Usage: infra/cloud-run/deploy-test-nodes.sh [PROJECT_ID] [REGION]
# The expert access code is read from EXPERT_ACCESS_TOKEN, or generated once and kept in
# .env.test-nodes.local (git-ignored).

PROJECT_ID="${1:-project-52e7ca23-228b-4cfd-879}"
REGION="${2:-asia-south1}"
MH_SERVICE="kisanai-c2c-test"
PB_SERVICE="kisanai-node-pb"

SECRETS_FILE=".env.test-nodes.local"
if [ -z "${EXPERT_ACCESS_TOKEN:-}" ]; then
  if [ -f "${SECRETS_FILE}" ]; then
    EXPERT_ACCESS_TOKEN=$(grep -E "^EXPERT_ACCESS_TOKEN=" "${SECRETS_FILE}" | cut -d '=' -f2-)
  else
    EXPERT_ACCESS_TOKEN=$(openssl rand -hex 12)
    echo "EXPERT_ACCESS_TOKEN=${EXPERT_ACCESS_TOKEN}" > "${SECRETS_FILE}"
    echo "Generated an expert access code in ${SECRETS_FILE}"
  fi
fi

PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
MH_URL="https://${MH_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
PB_URL="https://${PB_SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"

# APP_ENV=development because demo nodes keep data in SQLite; production requires Firestore + GCS.
# Env vars are joined with "@" (gcloud's ^@^ delimiter) so values such as NODE_SUBDIVISIONS keep their commas.
COMMON="APP_ENV=development@AUTH_MODE=local@STORE_PROVIDER=sqlite@SQLITE_PATH=/tmp/kisanai.sqlite3@MEDIA_PROVIDER=local@MEDIA_DIRECTORY=/tmp/media"
COMMON="${COMMON}@AI_ENABLED=true@AI_PROVIDER=vertex@GEMINI_MODEL=gemini-3.5-flash@GEMINI_FALLBACK_MODEL=gemini-3.7-flash@VERTEX_LOCATION=${REGION}"
COMMON="${COMMON}@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}@EARTH_ENGINE_ENABLED=true@SPEECH_ENABLED=true@OPEN_METEO_ENABLED=true@IMD_ENABLED=true"
COMMON="${COMMON}@EXPERT_ACCESS_TOKEN=${EXPERT_ACCESS_TOKEN}"

deploy() {
  local service="$1" env="$2"
  echo "Deploying ${service} (${PROJECT_ID}, ${REGION})..."
  # One warm instance keeps the SQLite demo data between requests; it resets on redeploy.
  gcloud run deploy "${service}" \
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
    --timeout=120 \
    --set-env-vars="^@^${env}"
}

deploy "${MH_SERVICE}" "${COMMON}@NODE_ID=india-node-mh@NODE_LABEL=Maharashtra and Uttar Pradesh node@NODE_SUBDIVISIONS=IN-MH,IN-UP@PUBLIC_BASE_URL=${MH_URL}@PEER_NODES=${PB_URL}"
deploy "${PB_SERVICE}" "${COMMON}@NODE_ID=india-node-pb@NODE_LABEL=Punjab node@NODE_SUBDIVISIONS=IN-PB@PUBLIC_BASE_URL=${PB_URL}@PEER_NODES=${MH_URL}"

echo "Nodes:"
echo "  ${MH_URL}/.well-known/agrin-node"
echo "  ${PB_URL}/.well-known/agrin-node"
