param(
  [Parameter(Mandatory=$true)][string]$ProjectId,
  [string]$Region = "asia-south1",
  [string]$Service = "qms-genai",
  [string]$EnvFile = "deploy/cloudrun/env.yaml",
  [string]$Secrets = "SECRET_KEY=qms-secret-key:latest,SF_API_KEY=qms-sf-api-key:latest,SF_WEBHOOK_SECRET=qms-sf-webhook-secret:latest,AI_GROQ_API_KEY=qms-groq-api-key:latest"
)

gcloud config set project $ProjectId
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

gcloud run deploy $Service `
  --source . `
  --region $Region `
  --allow-unauthenticated `
  --memory 2Gi `
  --cpu 1 `
  --concurrency 20 `
  --min-instances 0 `
  --max-instances 2 `
  --timeout 300 `
  --env-vars-file $EnvFile `
  --set-secrets $Secrets
