# Cloud Run deployment

```bash
bash infra/cloud-run/deploy.sh project-52e7ca23-228b-4cfd-879 asia-south1
```

Builds the root `Dockerfile` with Cloud Build and deploys the `kisanai-c2c` service. Settings are passed as environment variables in the script. Notes:

- Data lives in Firestore database `kisanai-ag02` (asia-south1) and uploaded photos in bucket `<project>-kisanai-ag02`, so nothing is lost on a new revision.
- The runtime service account has `roles/datastore.user` limited by an IAM condition to that one database.
- Session affinity keeps a farmer's Krishi Mitra chat on the same instance (chat memory is in-process and expires after 5 minutes).
- IMD warnings are off until IMD API credentials are added.
- The service account needs Vertex AI, Earth Engine and Speech/Text-to-Speech access.
- Expert review is open to everyone for the demo. To lock it later, set `EXPERT_ACCESS_CODE` on the service; the expert screen then asks for that code.
