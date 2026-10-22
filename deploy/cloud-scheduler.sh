#!/bin/bash
# =============================================================================
# Create Cloud Scheduler job for daily Telegram reports
# Run this once after deploying to Cloud Run.
# =============================================================================

set -euo pipefail

# --- Configuration ---
PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
CLOUD_RUN_URL="${CLOUD_RUN_URL:?Set CLOUD_RUN_URL}"  # e.g., https://messenger-agent-xxxxx.run.app
INTERNAL_API_TOKEN="${INTERNAL_API_TOKEN:?Set INTERNAL_API_TOKEN}"
REGION="us-central1"

echo "Creating Cloud Scheduler job for daily reports..."

gcloud scheduler jobs create http daily-perfume-report \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --schedule="0 22 * * *" \
    --time-zone="Asia/Amman" \
    --uri="${CLOUD_RUN_URL}/internal/daily-report" \
    --http-method=POST \
    --headers="X-Internal-Token=${INTERNAL_API_TOKEN},Content-Type=application/json" \
    --message-body='{}' \
    --attempt-deadline=60s \
    --description="Send the daily order list for the delivery company to Telegram at 10 PM Amman time"

echo "✅ Cloud Scheduler job created successfully."
echo "   Schedule: Daily at 22:00 Asia/Amman"
echo "   Target:   ${CLOUD_RUN_URL}/internal/daily-report"
