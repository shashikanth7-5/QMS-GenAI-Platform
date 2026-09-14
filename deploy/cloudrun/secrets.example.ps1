# Run after `gcloud auth login` and `gcloud config set project <PROJECT_ID>`.
# Replace placeholder values locally. Do not commit real secrets.

$secrets = @{
  "qms-secret-key" = "replace-with-64-plus-random-characters"
  "qms-sf-api-key" = "replace-with-your-SF_API_KEY"
  "qms-sf-webhook-secret" = "replace-with-your-SF_WEBHOOK_SECRET"
  "qms-groq-api-key" = "replace-with-your-Groq-key"
  "qms-openai-api-key" = ""
  "qms-gemini-api-key" = ""
  "qms-anthropic-api-key" = ""
}

foreach ($name in $secrets.Keys) {
  if ([string]::IsNullOrWhiteSpace($secrets[$name])) {
    continue
  }
  $secrets[$name] | gcloud secrets create $name --data-file=-
}
