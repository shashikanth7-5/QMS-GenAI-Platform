# Render Demo Survival Plan

Use this when the goal is a short business demo on a free or low-memory Render
service. This is not the final production architecture.

## Recommended path for the 3-day demo

Use Render again, but keep the runtime small:

- Runtime: Docker
- Instance: free or starter
- Workers: 1
- Threads: 2
- Disk: persistent disk if available
- Database: SQLite only for demo; PostgreSQL for real production

Set these environment variables:

```text
WEB_CONCURRENCY=1
WEB_THREADS=2
WEB_TIMEOUT=180
MOCK_MODE=false
AI_PROVIDER=groq
AI_GROQ_MODEL=openai/gpt-oss-120b
AI_FAILOVER_PROVIDERS=openai,gemini,anthropic
LLM_MAX_RETRIES=1
LLM_TIMEOUT_SECONDS=45
QMS_DATA_DIR=/app/data
DATABASE_URL=sqlite:////app/data/qms_data.db
UPLOAD_STORAGE_DIR=/app/data/uploads
CHROMA_PERSIST_DIR=/app/data/chroma_db
RATE_LIMIT_ENABLED=false
AGENT_SUPERVISOR_INTERVAL_SECONDS=3600
```

Keep Salesforce tenant settings:

```text
BOOTSTRAP_SF_TENANT=true
SF_TENANT_ID=sf-sandbox
SF_TENANT_DISPLAY=Salesforce Sandbox
SF_ORIGIN=<Salesforce My Domain URL>
SF_API_KEY=<same value used in Salesforce Named Credential password>
SF_WEBHOOK_SECRET=<same value used in QMS Settings custom setting>
```

Secrets:

```text
SECRET_KEY=<64+ char random>
AI_GROQ_API_KEY=<Groq key>
AI_OPENAI_API_KEY=<optional failover>
AI_GEMINI_API_KEY=<optional failover>
AI_ANTHROPIC_API_KEY=<optional failover>
```

## Why this helps

The old default used two Gunicorn workers. On a 512 MB service, each worker can
load a separate Python application process, so memory is duplicated. One worker
with two threads is slower but much more stable for a demo.

Document parsing libraries are now imported lazily, so the app does not load
PDF/Excel/Word parsers unless a user uploads that file type.

## Demo usage rules

- Do not click RCA model generation repeatedly; Groq free tier can return HTTP
  429.
- Warm the app before Salesforce demo by opening `/healthz`.
- Use one Salesforce Case at a time.
- Prefer `Create CAPA with AI` from Salesforce, then review in QMS.
- Avoid uploading large PDFs during the live demo.

## Free alternatives

| Platform | Fit | Notes |
|---|---|---|
| Render free | Good if optimized | 512 MB can work with one worker. Sleep/cold starts are expected. |
| Railway trial | Good short-term | Trial can provide up to 1 GB RAM, but trial/network behavior depends on account verification. |
| Koyeb free | Risky | Free instance is also 512 MB. Similar memory limit as Render. |
| Fly.io | Possible | Usually needs card/account setup and careful volume config. |
| Hugging Face Spaces | Not ideal | Good for demos, less natural for Flask + Salesforce callbacks. |

For this weekend, Render with one worker is the lowest-friction option.

## Production recommendation

After business approval, move to the business cloud team's platform with:

- PostgreSQL managed database
- Redis for rate limiting/background jobs
- 1-2 GB memory minimum for the web container
- persistent object storage for uploads
- provider failover keys configured
