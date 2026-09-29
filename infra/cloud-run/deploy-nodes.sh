#!/usr/bin/env bash
set -euo pipefail

# Deploys the KISANAI AgriN nodes as separate Cloud Run services. Each keeps its data in its own
# region and gets a daily Cloud Scheduler job that publishes shareable data to BigQuery.
#   kisanai-in-mh     India, Maharashtra              asia-south1 (Mumbai)
#   kisanai-in-north  India, Punjab + Uttar Pradesh   asia-south2 (Delhi)
#   kisanai-br-pr     Brazil, Paraná                  southamerica-east1 (São Paulo)
# The earlier kisanai-c2c service is not touched.
#
# One-time resources per node (see infra/cloud-run/README.md): Firestore database kisanai-<node>,
# bucket <project>-kisanai-<node>, secret kisanai-expert-code-<node>; service accounts kisanai-node and
# kisanai-scheduler; the BigQuery dataset is created on first publish and listed in Analytics Hub.
#
# Usage: infra/cloud-run/deploy-nodes.sh [PROJECT_ID] [in-mh|in-north|br-pr]   (second argument: one node only)

PROJECT_ID="${1:-project-52e7ca23-228b-4cfd-879}"
ONLY="${2:-all}"
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
NODE_SA="kisanai-node@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="kisanai-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"

url() { echo "https://kisanai-$1-${PROJECT_NUMBER}.$2.run.app"; }
IN_MH_URL=$(url in-mh asia-south1)
IN_NORTH_URL=$(url in-north asia-south2)
BR_PR_URL=$(url br-pr southamerica-east1)

# Env vars are joined with "|" (gcloud's ^|^ delimiter) so list values keep their commas.
COMMON="APP_ENV=production|GOOGLE_CLOUD_PROJECT=${PROJECT_ID}|STORE_PROVIDER=firestore|MEDIA_PROVIDER=gcs"
COMMON="${COMMON}|AI_ENABLED=true|AI_PROVIDER=vertex|GEMINI_MODEL=gemini-3.5-flash|GEMINI_FALLBACK_MODEL=gemini-3.7-flash"
COMMON="${COMMON}|EARTH_ENGINE_ENABLED=true|SPEECH_ENABLED=true|OPEN_METEO_ENABLED=true|JOB_SERVICE_ACCOUNT=${SCHEDULER_SA}"

deploy() {
  local node="$1" region="$2" url="$3" env="$4"
  [ "${ONLY}" = "all" ] || [ "${ONLY}" = "${node}" ] || return 0
  local dataset="agrin_${node//-/_}"
  echo "Deploying kisanai-${node} (${PROJECT_ID}, ${region})..."
  gcloud run deploy "kisanai-${node}" \
    --project="${PROJECT_ID}" --region="${region}" --source="." \
    --service-account="${NODE_SA}" --allow-unauthenticated --port=8080 \
    --memory=1Gi --cpu=1 --concurrency=40 --min-instances=1 --max-instances=3 --timeout=120 \
    --set-secrets="EXPERT_ACCESS_TOKEN=kisanai-expert-code-${node}:latest" \
    --set-env-vars="^|^${COMMON}|FIRESTORE_DATABASE=kisanai-${node}|MEDIA_BUCKET=${PROJECT_ID}-kisanai-${node}|BIGQUERY_DATASET=${dataset}|BIGQUERY_LOCATION=${region}|PUBLIC_BASE_URL=${url}|${env}"
  local args=(--project="${PROJECT_ID}" --location="${region}" --schedule="15 2 * * *" --time-zone="UTC"
              --uri="${url}/api/v1/internal/publish" --http-method=POST
              --oidc-service-account-email="${SCHEDULER_SA}" --oidc-token-audience="${url}/api/v1/internal/publish")
  gcloud scheduler jobs create http "kisanai-${node}-publish" "${args[@]}" 2>/dev/null \
    || gcloud scheduler jobs update http "kisanai-${node}-publish" "${args[@]}"
}

deploy in-mh asia-south1 "${IN_MH_URL}" "NODE_ID=india-node-mh|NODE_LABEL=India - Maharashtra node|NODE_COUNTRY_CODE=IN|NODE_SUBDIVISIONS=IN-MH|NODE_LANGUAGES=mr-IN,hi-IN,en-IN|DEFAULT_LOCALE=mr-IN|VERTEX_LOCATION=asia-south1|IMD_ENABLED=true|PEER_NODES=${IN_NORTH_URL},${BR_PR_URL}"
deploy in-north asia-south2 "${IN_NORTH_URL}" "NODE_ID=india-node-north|NODE_LABEL=India - Punjab and Uttar Pradesh node|NODE_COUNTRY_CODE=IN|NODE_SUBDIVISIONS=IN-PB,IN-UP|NODE_LANGUAGES=pa-IN,hi-IN,en-IN|DEFAULT_LOCALE=hi-IN|VERTEX_LOCATION=asia-south1|IMD_ENABLED=true|PEER_NODES=${IN_MH_URL},${BR_PR_URL}"
deploy br-pr southamerica-east1 "${BR_PR_URL}" "NODE_ID=brazil-node-pr|NODE_LABEL=Brazil - Paraná node|NODE_COUNTRY_CODE=BR|NODE_SUBDIVISIONS=BR-PR|NODE_LANGUAGES=pt-BR,en-IN|DEFAULT_LOCALE=pt-BR|VERTEX_LOCATION=global|IMD_ENABLED=false|PEER_NODES=${IN_MH_URL},${IN_NORTH_URL}"

echo "Nodes:"
echo "  ${IN_MH_URL}"
echo "  ${IN_NORTH_URL}"
echo "  ${BR_PR_URL}"
echo "Expert codes: Secret Manager secrets kisanai-expert-code-<node>."
