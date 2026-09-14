# Google Cloud Run Deployment

Use Cloud Run for the weekend pilot. It runs the existing Docker container without
managing Kubernetes nodes. GKE/Kubernetes is useful later only if the app needs
multiple internal services, private networking, or long-running workers at scale.

## 1. Create Google Cloud Project

1. Open Google Cloud Console.
2. Create or select a project.
3. Enable billing. Cloud Run has a monthly free tier, but Google still requires
   billing to be enabled.
4. Install or open Google Cloud Shell. Cloud Shell already has `gcloud`.

Recommended pilot region:

```text
asia-south1
```

## 2. Prepare Runtime Values

Reuse these values from Render:

- `MOCK_MODE=false`
- `AI_PROVIDER=groq`
- `AI_GROQ_API_KEY`
- `AI_GROQ_MODEL=openai/gpt-oss-120b`
- `AI_FAILOVER_PROVIDERS=openai,gemini,anthropic`
- `SF_API_KEY`
- `SF_WEBHOOK_SECRET`
- `SF_TENANT_ID=sf-sandbox`
- `SF_ORIGIN=https://orgfarm-8fbe692a55-dev-ed.develop.my.salesforce.com`

Create local env file:

```powershell
Copy-Item deploy/cloudrun/env.yaml.example deploy/cloudrun/env.yaml
```

Edit `deploy/cloudrun/env.yaml`. Do not commit real secrets.

## 3. Create Secrets

Use Secret Manager for values that must not be visible in the Cloud Run service
definition.

```powershell
Copy-Item deploy/cloudrun/secrets.example.ps1 deploy/cloudrun/secrets.ps1
notepad deploy/cloudrun/secrets.ps1
.\deploy\cloudrun\secrets.ps1
```

Secrets to create:

- `qms-secret-key`
- `qms-sf-api-key`
- `qms-sf-webhook-secret`
- `qms-groq-api-key`
- optional failover keys: `qms-openai-api-key`, `qms-gemini-api-key`,
  `qms-anthropic-api-key`

The default deploy script references only the required secrets. When failover
keys are ready, pass a wider `-Secrets` value:

```powershell
.\deploy\cloudrun\deploy.ps1 `
  -ProjectId "<PROJECT_ID>" `
  -Secrets "SECRET_KEY=qms-secret-key:latest,SF_API_KEY=qms-sf-api-key:latest,SF_WEBHOOK_SECRET=qms-sf-webhook-secret:latest,AI_GROQ_API_KEY=qms-groq-api-key:latest,AI_OPENAI_API_KEY=qms-openai-api-key:latest,AI_GEMINI_API_KEY=qms-gemini-api-key:latest,AI_ANTHROPIC_API_KEY=qms-anthropic-api-key:latest"
```

## 4. Deploy From Source

```powershell
.\deploy\cloudrun\deploy.ps1 -ProjectId "<PROJECT_ID>" -Region "asia-south1"
```

This uses:

- 2 GiB memory to avoid the Render memory issue.
- 1 vCPU.
- max 2 instances for cost control.
- min 0 instances so idle cost stays low.
- 300 second timeout for first cold LLM calls.

Cloud Run will print a service URL like:

```text
https://qms-genai-xxxxx-as.a.run.app
```

## 5. Verify QMS

Open:

```text
https://<cloud-run-url>/healthz
https://<cloud-run-url>/api/health
```

Expected:

- `/healthz` returns success.
- `/api/health` shows `llm.liveReady=true`.
- Header shows `Live LLM: groq / openai/gpt-oss-120b` after login.

## 6. Update Salesforce For Cloud Run

In Salesforce Setup:

1. Named Credential `QMS_GenAI`
   - URL: Cloud Run URL
   - Username: `sf-sandbox`
   - Password: same `SF_API_KEY`
   - Generate Authorization Header: unchecked
   - Allow Merge Fields in HTTP Header: checked
2. Custom Settings > QMS Settings > Manage > Org Default
   - `Api Host`: Cloud Run URL
   - `Tenant Id`: `sf-sandbox`
   - `Webhook Secret`: same `SF_WEBHOOK_SECRET`

## 7. Smoke Test

In Salesforce Developer Console:

```apex
Id caseId = '<CASE_ID>';
Map<String, Object> result = QmsGenAiClient.runAgentPipeline(caseId, true);
System.debug('Agent pipeline response: ' + JSON.serializePretty(result));
```

Expected:

- HTTP status `201`.
- response `status=success`.
- `capa.saved.created=true` or existing active draft reused.
- `capa.draft._provider=groq`.

## 8. Persistence Warning

The default pilot setup uses SQLite under `/app/data`. Cloud Run instances can
restart, and container filesystem is not durable. For production, use Cloud SQL
PostgreSQL and set:

```text
DATABASE_URL=postgresql+psycopg2://<user>:<password>@/<db>?host=/cloudsql/<INSTANCE_CONNECTION_NAME>
```

For the weekend demo, SQLite is acceptable only for smoke testing. For real
multi-user production, move to Cloud SQL before go-live.
