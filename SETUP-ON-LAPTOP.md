# Setting up KISANAI on the laptop

This folder is the full project: code, git history and all branches, `.env.local` with the API keys, deploy scripts and local run settings. The Google Cloud and GitHub sign-ins are not included (they are tied to this Mac); signing in again takes about two minutes.

Keep this zip private: `.env.local` holds real API keys.

## 1. Install the tools

- Python 3.12 or newer (`python3 --version`)
- Node.js 20 or newer (`node --version`)
- Google Cloud CLI: https://cloud.google.com/sdk/docs/install
- Git, and optionally the GitHub CLI (`gh`)

## 2. Sign in to Google Cloud

```bash
gcloud auth login vaibhav.kurkute4@gmail.com
gcloud auth application-default login
gcloud config configurations create kisanai
gcloud config set account vaibhav.kurkute4@gmail.com
gcloud config set project project-52e7ca23-228b-4cfd-879
gcloud config set run/region asia-south1
gcloud auth application-default set-quota-project project-52e7ca23-228b-4cfd-879
```

The second command lets the app on your laptop use Firestore, Cloud Storage, Earth Engine, Gemini (Vertex AI) and Speech with your account.

On this Mac the default gcloud project is a different one, so every command in the project scripts passes `--project=project-52e7ca23-228b-4cfd-879`. Keep doing that.

## 3. Sign in to GitHub

```bash
gh auth login
git config --global user.name "Vaibhav Bhausaheb Kurkute"
git config --global user.email "vaibhavdesign@gmail.com"
```

Without the GitHub CLI, the first `git push` asks you to sign in in the browser.

The repository is https://github.com/vaibhavdes/kisanAIC2C. The remote is already set in `.git/config`.

| Branch | What it is |
|---|---|
| `finale/ag02-improvements` | The hack2ignite AG-02 finale app. Work here. |
| `main` | The original AG-02 submission. Leave as is. |
| `test/agrin-track4-improvements` | Code for Communities Track 4 entry (separate project). Do not mix. |

## 4. Install and run locally

```bash
cd "KISANAI C2C"
python3 -m pip install -e "services/api[dev]"
cd apps/web && npm install && cd ../..
```

Run with a local SQLite database (safe for experiments):

```bash
PYTHONPATH=services/api/src EARTH_ENGINE_ENABLED=true IMD_ENABLED=false \
GOOGLE_CLOUD_PROJECT=project-52e7ca23-228b-4cfd-879 VERTEX_LOCATION=asia-south1 GEMINI_MODEL=gemini-2.5-flash \
SQLITE_PATH=./local.sqlite3 MEDIA_DIRECTORY=./local-media \
python3 -m uvicorn kisanai_c2c.main:app --host 127.0.0.1 --port 8090
```

Open http://localhost:8090. To run against the live Firestore data instead, add `STORE_PROVIDER=firestore FIRESTORE_DATABASE=kisanai-ag02 MEDIA_PROVIDER=gcs MEDIA_BUCKET=project-52e7ca23-228b-4cfd-879-kisanai-ag02` (changes then show up on the live app too).

`.claude/launch.json` has the same run settings for Claude Code, but its database paths point to folders on this Mac; change `SQLITE_PATH` and `MEDIA_DIRECTORY` to folders on the laptop.

## 5. Test, build and deploy

```bash
PYTHONPATH=services/api/src python3 -m pytest -q services/api/tests
cd apps/web && npm run build && cd ../..
rm -rf static/assets && cp -R apps/web/dist/assets static/assets && cp apps/web/dist/index.html static/index.html
bash infra/cloud-run/deploy.sh project-52e7ca23-228b-4cfd-879 asia-south1
```

The app serves the built frontend from `static/`, so rebuild and copy it before every deploy.

To go back to the last known-good version if a deploy breaks something:

```bash
gcloud run services update-traffic kisanai-c2c --to-revisions=kisanai-c2c-00023-5n8=100 --region=asia-south1 --project=project-52e7ca23-228b-4cfd-879
```

## 6. Google Cloud resources used by the app

| Resource | Name |
|---|---|
| Project | `project-52e7ca23-228b-4cfd-879` (number 313370978552) |
| Cloud Run service | `kisanai-c2c`, region `asia-south1` |
| Live URL | https://kisanai-c2c-313370978552.asia-south1.run.app |
| Firestore database | `kisanai-ag02` (asia-south1) |
| Storage bucket | `gs://project-52e7ca23-228b-4cfd-879-kisanai-ag02` (photos, satellite map images) |
| Runtime account | `313370978552-compute@developer.gserviceaccount.com` (Firestore limited to `kisanai-ag02`, Earth Engine writer) |
| Current revision | `kisanai-c2c-00023-5n8` |

Do not point the AG-02 app at the Track 4 databases (`kisanai-in-mh`, `kisanai-in-north`, `kisanai-br-pr`).

Demo farms in Firestore: Zadgaon Cotton Farm (Yavatmal), Sangamner Sugarcane Farm (Ahmednagar), Wagholi Farm (Pune). They were created from this Mac, so only this Mac (or an expert) can edit or delete them.

## 7. Notes for Claude Code

`.claude/memory/` holds the notes Claude kept about this project (resources, branch rules, no Claude attribution in commits). To use them on the laptop, copy the files into Claude Code's memory folder for the project, under `~/.claude/projects/<project-path>/memory/`.
