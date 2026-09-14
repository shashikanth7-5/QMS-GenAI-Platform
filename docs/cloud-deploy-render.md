# Cloud Deploy on Render.com — free-tier pilot guide

This guide takes you from an empty Render account to a live QMS GenAI
Platform that Salesforce sandbox can call. **No CLI install required** —
everything is done through the Render web console.

Estimated time: **45 minutes**.

Estimated cost:
- Blueprint free tier: **$0/month** — web sleeps after 15 min idle, Postgres expires after 90 days
- Paid pilot promote: **~$24/month** (web + Postgres + Redis on Starter plans)

---

## Why Render (and not AWS/GCP for the pilot)

| Requirement | Render Free Tier | AWS Free Tier | GCP Free Tier |
|---|---|---|---|
| Web hosting with HTTPS | ✅ Free forever (sleep-on-idle) | ✅ EC2 t2.micro 12 mo | ✅ Cloud Run 2M requests/mo |
| Managed Postgres | ✅ Free 90 days | ✅ RDS db.t3.micro 12 mo | ❌ Cloud SQL not free |
| GitHub-based deploy | ✅ No CLI needed | ⚠️ Needs `aws` CLI | ⚠️ Needs `gcloud` CLI |
| Corporate laptop friendly | ✅ Web-only | ❌ CLI required | ❌ CLI required |
| Time to first deploy | 15 min | 2–4 hours | 1–2 hours |
| Card required for signup | ❌ | ✅ | ✅ |

For a pilot / demo running on an office laptop where IT blocks CLI
installs, Render wins on speed and access. Move to GCP Cloud Run or
AWS EKS when you're ready for enterprise-grade production.

---

## Phase 1 — Prerequisites (10 min)

### 1.1 GitHub account
You already have `Shashikanth7-5/QMS-GenAI-Platform`. If your Cognizant
laptop can't access GitHub via SSH, that's fine — Render uses HTTPS +
OAuth in a browser.

### 1.2 Sign up for Render
1. Go to **https://render.com/register**
2. Click **Sign in with GitHub** (recommended — no separate password to manage)
3. Authorize Render to access your GitHub account (read-only for public repos, or grant access to `QMS-GenAI-Platform` explicitly)

### 1.3 Anthropic (or OpenAI) API key
Already covered in the previous guide — get one from https://console.anthropic.com/ and keep it handy for Phase 2.5.

---

## Phase 2 — Deploy via Blueprint (15 min)

### 2.1 Trigger the Blueprint deploy
1. In Render dashboard → **New +** (top right) → **Blueprint**
2. Under "Connect a repository", find `QMS-GenAI-Platform` in the list.
   - If it's not listed, click **Configure account** → grant Render access to that repo → refresh.
3. Click **Connect**.

### 2.2 Render reads `render.yaml`
You'll see a page like:
```
Blueprint qms-genai-platform
├── qms-web  (Web service, Docker)
└── qms-data (persistent disk mounted at /app/data)
```

### 2.3 Fill the required secret values
Render prompts for the two values marked `sync: false` in `render.yaml`:

| Variable | What to paste |
|---|---|
| `AI_API_KEY` | Your Groq/Anthropic/OpenAI/Gemini key |
| `AI_PROVIDER` | Default is `anthropic`; use `groq`, `openai`, or `gemini` as needed |

Click **Apply**.

### 2.4 Wait for the first build
Render will:
1. Attach the persistent disk at `/app/data`
2. Clone your repo and run `docker build` (~4–6 min first time — subsequent builds cached)
3. Initialize SQLite tables at `/app/data/qms_data.db`
4. Persist ChromaDB under `/app/data/chroma_db`
5. Health check on `/healthz` — service goes green when it passes

Watch the **Logs** tab. Look for:
```
INFO [database] db.configured
INFO [app] app.startup.complete
[INFO] Listening at: http://0.0.0.0:5000
```
For SQLite pilot deployments, confirm these env vars point to the mounted disk:
`QMS_DATA_DIR=/app/data`, `DATABASE_URL=sqlite:////app/data/qms_data.db`,
`CHROMA_PERSIST_DIR=/app/data/chroma_db`, and `UPLOAD_STORAGE_DIR=/app/data/uploads`.

### 2.5 Note your public URL
Once green, Render shows your public HTTPS URL at the top of the service page:
```
https://qms-web-xxxx.onrender.com
```
**Copy this URL — this is your production QMS endpoint.**

---

## Phase 3 — Bootstrap the app (5 min)

### 3.1 Create the first admin user
Since `SEED_BUILTIN_USERS=false` in render.yaml, there's no `admin/admin`
account. You need to create one via the Render Shell:

1. In your `qms-web` service page → **Shell** tab (left sidebar) → **Launch Shell**
2. Run:
   ```bash
   python -c "
   from database import SessionLocal, init_db
   from models import UserModel
   from werkzeug.security import generate_password_hash
   init_db()
   with SessionLocal() as s:
       u = UserModel(username='admin', email='you@example.com',
                     password_hash=generate_password_hash('CHANGE-THIS-STRONG-PW'),
                     role='admin', full_name='QMS Admin', status='approved')
       s.add(u); s.commit()
       print('created admin:', u.id)
   "
   ```
   **Replace `CHANGE-THIS-STRONG-PW` with something strong. Save it.**

### 3.2 Verify login
Open your Render URL in a browser → login with `admin / <your password>`. You should see the dashboard.

---

## Phase 4 — Provision a Salesforce tenant (5 min)

Still in the Render Shell:
```bash
python -m scripts.provision_tenant \
  --tenant sf-sandbox \
  --display "Salesforce Sandbox" \
  --origins "https://YOUR-DOMAIN.develop.my.salesforce.com"
```

Replace `YOUR-DOMAIN.develop.my.salesforce.com` with **your** Salesforce
My Domain URL (the one you have handy).

**Copy the three values printed — you cannot retrieve them again:**
```
X-Tenant-Id:     sf-sandbox
X-API-Key:       <32-byte token>
webhook_secret:  <32-byte token>
```

---

## Phase 5 — Deploy Apex + LWC to Salesforce (10 min)

You can't run `sf` CLI on the corp laptop. Two workarounds:

### Option A — Use Salesforce Setup web UI (recommended, no CLI)

1. In your SF sandbox → **Setup** → **Custom Code** → **Apex Classes** → **New**
   - Copy-paste contents of `deploy/salesforce/QmsGenAiClient.cls` from GitHub → **Save**
   - Repeat for `QmsWebhookSender.cls`, `QmsGenAiClientTest.cls`, `QmsWebhookSenderTest.cls`
2. **Custom Settings** → **New**
   - Object Name: `QmsSettings`
   - Setting Type: `Hierarchy`
   - Add fields: `Webhook_Secret__c` (Text 255), `Tenant_Id__c` (Text 80), `Api_Host__c` (URL 255)
3. **Lightning Components** → won't work from Setup UI. For LWC you need
   either:
   - **Option A1**: Skip the LWC for now — test with Anonymous Apex (see Phase 6)
   - **Option A2**: Use **Salesforce DevOps Center** (browser-based, no
     local CLI) — it can pull the LWC from your GitHub repo directly.
     Setup → DevOps Center → New Project → connect GitHub → deploy the
     `deploy/salesforce` folder.

### Option B — Ask a teammate with an unrestricted laptop to run `sf project deploy start` once. It's a 30-second command; they don't need to know the code.

---

## Phase 6 — Configure Salesforce (10 min)

Everything below is done in the SF sandbox web UI.

### 6.1 Populate the Custom Setting
Setup → **Custom Settings** → **QmsSettings** → **Manage** → **New** (creates Org Default):
- Webhook Secret: paste `webhook_secret` from Phase 4
- Tenant Id: `sf-sandbox`
- Api Host: your Render URL (e.g., `https://qms-web-xxxx.onrender.com`)
- **Save**

### 6.2 Named Credential
Setup → **Named Credentials** → **New Legacy**:
- Label: `QMS GenAI`
- Name: `QMS_GenAI`
- URL: your Render URL
- Identity Type: `Named Principal`
- Auth Protocol: `Password Authentication`
- Username: `sf-sandbox`
- Password: paste `X-API-Key` from Phase 4
- Generate Authorization Header: **UNCHECK**
- Allow Merge Fields in HTTP Header: **CHECK**
- **Custom Headers** (New Custom Header × 2):
  - `X-API-Key` = `{!$Credential.Password}`
  - `X-Tenant-Id` = `sf-sandbox`
- **Save**

### 6.3 Enable Case Origin picklist value (if not already)
Setup → Object Manager → **Case** → Fields & Relationships → **Origin** → **New** value `Medical Device` → **Save**

---

## Phase 7 — End-to-end smoke test (5 min)

### 7.1 Via Anonymous Apex (works even without the LWC)
In SF sandbox → **Developer Console** → **Debug** → **Open Execute Anonymous Window**:

```apex
Case c = new Case(
  Subject     = 'Pump seal leak - LOT-2026-001',
  Description = 'Batch failing pressure test at 5 bar; 3 units affected',
  Priority    = 'High',
  Origin      = 'Medical Device'
);
insert c;
Map<String, Object> result = QmsGenAiClient.generateCapa(c.Id);
System.debug('CAPA response: ' + JSON.serializePretty(result));
```
Check **Open Log** → Debug Only. You should see the CAPA JSON with
`rootCause`, `correctiveAction`, `preventiveAction`.

### 7.2 Verify in QMS
- Open your Render URL → login with the admin you created in Phase 3
- Dashboard should show a new quality record with the Case subject
- CAPA visible in `Under Review` status

### 7.3 Watch Render logs
Render service page → **Logs** tab → live tail. You'll see:
```
INFO api_v1.integrations.capa {caseId: "500..."}
INFO llm.call.completed {provider: "anthropic", cost_usd: 0.024, ...}
```

---

## What's live now (production-ready features)

Every Version@1/2/3 feature you tested locally is now running in the cloud:
- Multi-tenant API keys (HMAC-hashed, per-tenant rate limits)
- CSRF, XSS-safe templates, rate limiting
- Structured logs with `run_id` / `tenant_id` correlation
- Immutable audit trail (SHA-256 hash chain)
- LLM circuit breaker + cost tracking (`llm_call_logs` table)
- Dead-letter queue for failed agent runs
- Idempotency keys (retries don't duplicate CAPAs)
- Alembic-managed schema
- 21 CFR Part 11 e-signature on Approve/Reject
- Salesforce webhook receiver with HMAC-SHA256 signing + 5-min replay window
- TrackWise API v1 surface

---

## Post-deploy checklist

Once the smoke test passes, spend 15 minutes on these:

- [ ] **Rotate the admin password** — the initial one is in your shell history
- [ ] **Change `SEED_BUILTIN_USERS` to `false`** — already set in render.yaml, verify
- [ ] **Set a Redis add-on** if you want rate-limit persistence across restarts (Upstash Redis has a free 10k-command/day tier)
- [ ] **Upgrade Postgres to Starter plan** before day 90 to avoid data loss (or export + reimport)
- [ ] **Set up Render notifications** — service down alerts to Slack/email (Settings → Notifications)
- [ ] **Add a custom domain** if you want `qms.yourcompany.com` instead of `.onrender.com` (Settings → Custom Domains — free)

---

## Common issues + fixes

| Symptom | Cause | Fix |
|---|---|---|
| Blueprint fails at "Building" | `requirements.txt` install error | Check Logs — usually a version incompatibility. Update the offending pin. |
| First-request timeout (~30s) | Free tier sleep-on-idle | Normal. Upgrade to Starter plan ($7/mo) for always-on. |
| `alembic upgrade head` fails on startup | Postgres not reachable | Verify `DATABASE_URL` env var has `postgresql+psycopg2://` prefix |
| `401 Unauthorized` from SF callout | X-API-Key mismatch or trailing whitespace | Re-copy from Phase 4 output |
| SF Named Credential test button says success but Apex still gets 401 | The `Password` field is being auto-sent as Basic Auth | Confirm "Generate Authorization Header" is UNCHECKED |
| LLM returns 5xx | Wrong provider/key | Check `AI_PROVIDER` matches your key (`anthropic` for `sk-ant-…`) |
| Webhook signature 401 | Server clock drift | Not fixable client-side; Render's servers are NTP-synced, so this is usually SF sandbox latency > 5 min |

---

## Next milestones (post-pilot)

1. **CSP nonce hardening** — currently `'unsafe-inline'`; needs the template sweep before external audit
2. **RBAC on all mutating routes** — `admin_required` only covers CAPA today
3. **Grafana dashboard + alerts** — JSON is in `deploy/monitoring/`, needs a Prometheus scrape target on Render (or move to GCP Cloud Run + Managed Service for Prometheus)
4. **Redis in prod** — pilot works without it, but rate-limit + Celery need it for scale
5. **21 CFR Part 11 e-sig on Close transition** — Approve/Reject already gated; Close is not
6. **Playwright browser E2E tests** — would have caught the CSP nonce bug in CI

For each of these, open a small PR — no big-bang commits like `improvement-v1`.
