#!/usr/bin/env bash
# Runs inside the pipeline container.
# Sequence: scrape → dbt seed → dbt run → dbt test
# Each step logs clearly so you can see exactly where a failure occurred.

set -euo pipefail

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "━━━ Step 1/4: Scrapers ━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd /app
python -m scraper.run_all

log "━━━ Step 2/4: dbt seed ━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd /app/dbt_project
dbt seed --profiles-dir . --target prod --no-partial-parse

log "━━━ Step 3/4: dbt run ━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
dbt run --profiles-dir . --target prod --no-partial-parse

log "━━━ Step 4/4: dbt test ━━━━━━━━━━━━━━━━━━━━━━━━━━━"
dbt test --profiles-dir . --target prod

log "━━━ Pipeline complete ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
