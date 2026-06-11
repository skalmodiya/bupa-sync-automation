#!/bin/sh
# Wait for n8n to be fully ready (including owner setup), then import workflows.
# n8n discards workflow imports if no owner account exists yet, so we must
# wait until the owner is configured before importing.

echo "=== BUPA Sync n8n Workflow Importer ==="

MAX_RETRIES=60
RETRY_INTERVAL=5

# Phase 1: Wait for n8n web UI to respond
echo "Phase 1: Waiting for n8n web UI..."
attempt=0
until wget -qO /dev/null http://n8n:5678/ 2>/dev/null; do
  attempt=$((attempt + 1))
  if [ $attempt -ge $MAX_RETRIES ]; then
    echo "ERROR: n8n web UI not reachable after $MAX_RETRIES attempts. Exiting."
    exit 1
  fi
  echo "  n8n not ready, retrying ($attempt/$MAX_RETRIES)..."
  sleep $RETRY_INTERVAL
done
echo "n8n web UI is up."

# Phase 2: Wait for n8n owner setup to be complete.
# n8n returns a redirect to /setup when no owner exists.
# Once owner is configured (via env vars or manual setup), /healthz returns 200.
echo "Phase 2: Waiting for n8n owner setup to complete..."
attempt=0
until wget -qO /dev/null http://n8n:5678/healthz 2>/dev/null; do
  attempt=$((attempt + 1))
  if [ $attempt -ge $MAX_RETRIES ]; then
    echo "WARNING: n8n /healthz not responding after $MAX_RETRIES attempts."
    echo "Proceeding with import anyway..."
    break
  fi
  echo "  n8n owner not set up yet, retrying ($attempt/$MAX_RETRIES)..."
  sleep $RETRY_INTERVAL
done
echo "n8n is fully initialized."

# Phase 3: Wait for n8n CLI/database to be ready
echo "Phase 3: Verifying n8n CLI/database..."
attempt=0
until n8n list:workflow > /dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ $attempt -ge $MAX_RETRIES ]; then
    echo "ERROR: n8n CLI not ready after $MAX_RETRIES attempts. Exiting."
    exit 1
  fi
  echo "  n8n CLI not ready, retrying ($attempt/$MAX_RETRIES)..."
  sleep $RETRY_INTERVAL
done
echo "n8n CLI/database is ready."

# Phase 4: Import each workflow with per-file retries
IMPORT_RETRIES=5
echo ""
echo "Phase 4: Importing workflows..."

imported=0
failed=0

for f in /workflows/*.json; do
  if [ -f "$f" ]; then
    name=$(basename "$f" .json)
    attempt=0
    success=0
    while [ $attempt -lt $IMPORT_RETRIES ]; do
      attempt=$((attempt + 1))
      echo "  Importing: $name (attempt $attempt/$IMPORT_RETRIES)"
      if n8n import:workflow --input="$f" 2>&1; then
        success=1
        imported=$((imported + 1))
        echo "  OK: $name imported."
        break
      fi
      echo "  Retrying $name in ${RETRY_INTERVAL}s..."
      sleep $RETRY_INTERVAL
    done
    if [ $success -eq 0 ]; then
      echo "  FAILED: $name could not be imported after $IMPORT_RETRIES attempts."
      failed=$((failed + 1))
    fi
  fi
done

# Phase 5: Verify imports
echo ""
echo "Verifying imported workflows..."
n8n list:workflow 2>&1 || true

echo ""
echo "=== Import complete: $imported succeeded, $failed failed ==="
echo "Access n8n at http://localhost:5678"
echo "Default credentials: admin@bupa-sync.local / BupaSync2024!"
echo "Workflows are ready for activation via the n8n UI."

if [ $failed -gt 0 ]; then
  exit 1
fi
