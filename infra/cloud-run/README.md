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
