# Cloud Run Deployment (`infra/cloud-run`)

Deployment automation for the KISANAI C2C unified container service on Google Cloud Run.

## Live Deployment Info

- **Service**: `kisanai-c2c`
- **Current Live Revision**: `kisanai-c2c-00008-8r4`
- **Live Service URL**: `https://kisanai-c2c-313370978552.asia-south1.run.app`
- **GCP Project**: `project-52e7ca23-228b-4cfd-879`
- **Region**: `asia-south1` (Mumbai)
- **Container Port**: `8080`
- **Memory**: `1Gi`, **CPU**: `1`
- **Concurrency**: `8`, **Max Instances**: `3`

## Deploy Script

Deploy the application from source using:

```bash
bash infra/cloud-run/deploy.sh project-52e7ca23-228b-4cfd-879 asia-south1
```

The script builds the multi-stage `Dockerfile` (React build + Python runtime) in Cloud Build, pushes the container image to Google Artifact Registry, and deploys it to Cloud Run with full environment variables configured.

## Two-node test network

`deploy-test-nodes.sh` deploys two peer nodes as separate services, so the state network can be exercised without touching `kisanai-c2c`:

| Service | States | Peer |
|---|---|---|
| `kisanai-c2c-test` | IN-MH, IN-UP | `kisanai-node-pb` |
| `kisanai-node-pb` | IN-PB | `kisanai-c2c-test` |

```bash
bash infra/cloud-run/deploy-test-nodes.sh project-52e7ca23-228b-4cfd-879 asia-south1
```

The expert access code is generated once into `.env.test-nodes.local` (git-ignored). Both nodes keep demo data in SQLite on one warm instance, so data resets on redeploy. For durable data, enable Firestore and a GCS bucket and use `config/cloud-run.example.yaml`.

Demo of the exchange:
1. On `kisanai-c2c-test`, create a farm in Punjab; it gets the global baseline.
2. Open **Expert → State network**, import the Punjab crop calendar from `kisanai-node-pb` and approve it.
3. Refresh the farm's crops; they now follow the Punjab calendar.

Both deploy scripts require `EXPERT_ACCESS_TOKEN`.
