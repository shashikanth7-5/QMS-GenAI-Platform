# Salesforce CLI Deployment

Use this once Salesforce CLI is installed. This deploys the richer Salesforce
UI so users can stay inside Salesforce and invoke QMS GenAI services from Case
records.

## 1. Confirm CLI

```powershell
sf --version
```

## 2. Authorize Sandbox

```powershell
sf org login web --alias qms-sandbox --instance-url https://orgfarm-8fbe692a55-dev-ed.develop.my.salesforce.com
```

Confirm:

```powershell
sf org display --target-org qms-sandbox
```

## 3. Pull Latest Code

```powershell
git checkout main
git pull origin main
```

If Salesforce updates are still on a feature branch, checkout that branch
instead.

## 4. Deploy Salesforce Metadata

```powershell
sf project deploy start --source-dir deploy/salesforce --target-org qms-sandbox --wait 20
```

This deploys:

- `QmsGenAiClient`
- `QmsWebhookSender`
- `QmsCreateCapaFlowAction`
- `qmsCreateCapa` Lightning Web Component
- `QmsSettings__c` metadata

## 5. Run Apex Tests

```powershell
sf apex run test --target-org qms-sandbox --test-level RunLocalTests --wait 20 --code-coverage
```

Expected:

- `QmsGenAiClientTest` passes.
- `QmsWebhookSenderTest` passes.
- Overall coverage is above 75%.

## 6. Update Salesforce Settings

Setup > Named Credentials > `QMS_GenAI`:

- URL: Google Cloud Run URL
- Username: `sf-sandbox`
- Password: same value as `SF_API_KEY`
- Generate Authorization Header: unchecked
- Allow Merge Fields in HTTP Header: checked

Setup > Custom Settings > QMS Settings > Manage > Org Default:

- Tenant Id: `sf-sandbox`
- Api Host: Google Cloud Run URL
- Webhook Secret: same value as `SF_WEBHOOK_SECRET`

## 7. Create LWC Case Action

Setup > Object Manager > Case > Buttons, Links, and Actions > New Action:

- Action Type: Lightning Web Component
- Lightning Web Component: `c:qmsCreateCapa`
- Label: `Create CAPA with AI`
- Name: `Create_CAPA_with_AI`

Add it to:

```text
Case Page Layout > Salesforce Mobile and Lightning Experience Actions
```

## 8. Add Panel To Case Record Page

For the right-side embedded panel:

1. Setup > Object Manager > Case > Lightning Record Pages.
2. Edit the active Case record page.
3. Drag custom component `qmsCreateCapa` into the right sidebar.
4. Save and Activate.

## 9. Smoke Test

1. Open a real Case.
2. Click `Create CAPA with AI`.
3. Confirm Salesforce panel shows:
   - Root Cause Analysis
   - CAPA draft fields
   - Risk/owner/closure
   - LLM provider/model
   - Open in QMS
4. Confirm QMS dashboard lists one active CAPA for the Salesforce Case.

## 10. Known Pilot Gaps

- QMS creates and stores CAPA; Salesforce writeback fields are not complete yet.
- Separate `Run RCA Analysis` Salesforce action is next.
- Groq free tier can return HTTP 429; add provider failover keys for demos.
