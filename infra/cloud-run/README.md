# Cloud Run deployment

Each BRICS country node is its own Cloud Run service in its own region. [`deploy-nodes.sh`](deploy-nodes.sh) deploys:

| Service | Serves | Region | Firestore DB | Bucket | BigQuery dataset | Analytics Hub exchange |
|---|---|---|---|---|---|---|
| `kisanai-in-mh` | India, Maharashtra (`IN-MH`) | asia-south1 | `kisanai-in-mh` | `<project>-kisanai-in-mh` | `agrin_in_mh` | `brics_agrin_in` |
| `kisanai-in-north` | India, Punjab and Uttar Pradesh (`IN-PB`, `IN-UP`) | asia-south2 | `kisanai-in-north` | `<project>-kisanai-in-north` | `agrin_in_north` | `brics_agrin_in_north` |
| `kisanai-br-pr` | Brazil, Paraná (`BR-PR`) | southamerica-east1 | `kisanai-br-pr` | `<project>-kisanai-br-pr` | `agrin_br_pr` | `brics_agrin_br` |

```bash
bash infra/cloud-run/deploy-nodes.sh project-52e7ca23-228b-4cfd-879
```

The script also creates, or updates, a daily Cloud Scheduler job per node. The job calls `POST /api/v1/internal/publish` with a Google-signed OIDC token for `kisanai-scheduler@`, and the node verifies that token before publishing.

## One-time resources

```bash
P=project-52e7ca23-228b-4cfd-879
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com \
  earthengine.googleapis.com firestore.googleapis.com storage.googleapis.com translate.googleapis.com speech.googleapis.com \
  texttospeech.googleapis.com bigquery.googleapis.com analyticshub.googleapis.com cloudscheduler.googleapis.com \
  secretmanager.googleapis.com --project $P

# Per node (example: Brazil, Paraná)
gcloud firestore databases create --database=kisanai-br-pr --location=southamerica-east1 --type=firestore-native --project $P
gcloud storage buckets create gs://$P-kisanai-br-pr --location=southamerica-east1 --uniform-bucket-level-access --public-access-prevention --project $P
openssl rand -hex 16 | tr -d '\n' | gcloud secrets create kisanai-expert-code-br-pr --data-file=- --project $P
```

Service accounts:
- **`kisanai-node`** (the Cloud Run identity) has these roles:
  - Firestore user, Storage object user, Secret accessor;
  - Vertex AI user, Earth Engine writer (needed to render field thumbnails), Service usage consumer, Cloud Translation user;
  - BigQuery job user and data editor.
- **`kisanai-scheduler`** has no roles; it only signs the daily call.

The BigQuery dataset is created by the node's first publish. Each dataset is then listed in its region's Analytics Hub exchange (Analytics Hub needs the exchange and the dataset in the same region).

## Adding a state or a country

1. Build its agronomy pack with official sources (see `services/api/scripts/build_agronomy_packs.py`) and add practice write-ups to `data/practices/practice_library.json`.
2. Create the node's Firestore database, bucket and expert-code secret in the country's region.
3. Deploy with its own `NODE_ID`, `NODE_COUNTRY_CODE`, `NODE_SUBDIVISIONS`, `NODE_LANGUAGES` and `DEFAULT_LOCALE`. Languages without a hand-written dictionary are machine-translated automatically.
4. Add the new node's URL to the other nodes' `PEER_NODES`, and list its BigQuery dataset in an Analytics Hub exchange.

The expert access code for each node is in Secret Manager (`kisanai-expert-code-<node>`). The earlier `kisanai-c2c` service is separate and is not changed by this script.
