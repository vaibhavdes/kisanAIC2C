#!/usr/bin/env bash
set -euo pipefail

# Deploys the two BRICS AgriN country nodes as separate Cloud Run services, each keeping its data in
# its own region, and a daily Cloud Scheduler job per node that publishes shareable data to BigQuery:
#   kisanai-in-mh  - India, Maharashtra (asia-south1, Mumbai)
#   kisanai-br-pr  - Brazil, Paraná    (southamerica-east1, São Paulo)
# The existing kisanai-c2c service is not touched.
#
# One-time resources this script expects (created once, see infra/cloud-run/README.md):
#   Firestore databases kisanai-in-mh / kisanai-br-pr, buckets <project>-kisanai-in-mh / -br-pr,
#   secrets kisanai-expert-code-in-mh / -br-pr, service accounts kisanai-node and kisanai-scheduler,
#   BigQuery datasets agrin_in_mh / agrin_br_pr listed in Analytics Hub exchanges brics_agrin_in / brics_agrin_br.
#
# Usage: infra/cloud-run/deploy-nodes.sh [PROJECT_ID]

PROJECT_ID="${1:-project-52e7ca23-228b-4cfd-879}"
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
NODE_SA="kisanai-node@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="kisanai-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"

IN_SERVICE="kisanai-in-mh"; IN_REGION="asia-south1"
BR_SERVICE="kisanai-br-pr"; BR_REGION="southamerica-east1"
IN_URL="https://${IN_SERVICE}-${PROJECT_NUMBER}.${IN_REGION}.run.app"
BR_URL="https://${BR_SERVICE}-${PROJECT_NUMBER}.${BR_REGION}.run.app"

# Env vars are joined with "@" (gcloud's ^@^ delimiter) so list values keep their commas.
COMMON="APP_ENV=production@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}@STORE_PROVIDER=firestore@MEDIA_PROVIDER=gcs"
COMMON="${COMMON}@AI_ENABLED=true@AI_PROVIDER=vertex@GEMINI_MODEL=gemini-3.5-flash@GEMINI_FALLBACK_MODEL=gemini-3.7-flash"
COMMON="${COMMON}@EARTH_ENGINE_ENABLED=true@SPEECH_ENABLED=true@OPEN_METEO_ENABLED=true@JOB_SERVICE_ACCOUNT=${SCHEDULER_SA}"

deploy() {
  local service="$1" region="$2" env="$3"
  echo "Deploying ${service} (${PROJECT_ID}, ${region})..."
  gcloud run deploy "${service}" \
    --project="${PROJECT_ID}" \
    --region="${region}" \
    --source="." \
    --service-account="${NODE_SA}" \
    --allow-unauthenticated \
    --port=8080 \
    --memory=1Gi \
    --cpu=1 \
    --concurrency=40 \
    --min-instances=1 \
    --max-instances=3 \
    --timeout=120 \
    --set-secrets="EXPERT_ACCESS_TOKEN=kisanai-expert-code-${service#kisanai-}:latest" \
    --set-env-vars="^@^${env}"
}

schedule() {
  local service="$1" region="$2" url="$3"
  local args=(--project="${PROJECT_ID}" --location="${region}" --schedule="15 2 * * *" --time-zone="UTC"
              --uri="${url}/api/v1/internal/publish" --http-method=POST
              --oidc-service-account-email="${SCHEDULER_SA}" --oidc-token-audience="${url}/api/v1/internal/publish")
  gcloud scheduler jobs create http "${service}-publish" "${args[@]}" 2>/dev/null \
    || gcloud scheduler jobs update http "${service}-publish" "${args[@]}"
}

deploy "${IN_SERVICE}" "${IN_REGION}" "${COMMON}@NODE_ID=india-node-mh@NODE_LABEL=India - Maharashtra node@NODE_COUNTRY_CODE=IN@NODE_SUBDIVISIONS=IN-MH@NODE_LANGUAGES=mr-IN,hi-IN,en-IN@DEFAULT_LOCALE=mr-IN@VERTEX_LOCATION=${IN_REGION}@FIRESTORE_DATABASE=kisanai-in-mh@MEDIA_BUCKET=${PROJECT_ID}-kisanai-in-mh@BIGQUERY_DATASET=agrin_in_mh@BIGQUERY_LOCATION=${IN_REGION}@IMD_ENABLED=true@PUBLIC_BASE_URL=${IN_URL}@PEER_NODES=${BR_URL}"
deploy "${BR_SERVICE}" "${BR_REGION}" "${COMMON}@NODE_ID=brazil-node-pr@NODE_LABEL=Brazil - Paraná node@NODE_COUNTRY_CODE=BR@NODE_SUBDIVISIONS=BR-PR@NODE_LANGUAGES=pt-BR,en-IN@DEFAULT_LOCALE=pt-BR@VERTEX_LOCATION=global@FIRESTORE_DATABASE=kisanai-br-pr@MEDIA_BUCKET=${PROJECT_ID}-kisanai-br-pr@BIGQUERY_DATASET=agrin_br_pr@BIGQUERY_LOCATION=${BR_REGION}@IMD_ENABLED=false@PUBLIC_BASE_URL=${BR_URL}@PEER_NODES=${IN_URL}"

schedule "${IN_SERVICE}" "${IN_REGION}" "${IN_URL}"
schedule "${BR_SERVICE}" "${BR_REGION}" "${BR_URL}"

echo "Nodes:"
echo "  ${IN_URL}"
echo "  ${BR_URL}"
echo "Expert codes: Secret Manager secrets kisanai-expert-code-in-mh and kisanai-expert-code-br-pr."
