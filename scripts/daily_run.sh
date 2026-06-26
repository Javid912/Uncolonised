#!/usr/bin/env bash
# =============================================================
# daily_run.sh
# Runs every day via cron: scrape → dbt run → dbt test
#
# Add to crontab:
#   crontab -e
#   30 5 * * * /home/ubuntu/berlin-demos/scripts/daily_run.sh >> /var/log/berlin-demos.log 2>&1
#
# That runs at 05:30 each morning (the Police page updates twice daily).
# =============================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

echo "$LOG_PREFIX ── Starting daily run ──────────────────────"

# Load env vars from .env file
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# ── Step 1: Scrape ────────────────────────────────────────────
echo "$LOG_PREFIX Running scrapers…"
cd "$PROJECT_DIR"
source .venv/bin/activate
python -m scraper.run_all

# ── Step 2: dbt run ───────────────────────────────────────────
echo "$LOG_PREFIX Running dbt…"
cd "$PROJECT_DIR/dbt_project"
dbt run --profiles-dir . --target prod

# ── Step 3: dbt test (catches broken scrapes early) ───────────
echo "$LOG_PREFIX Running dbt tests…"
dbt test --profiles-dir . --target prod

echo "$LOG_PREFIX ── Daily run complete ──────────────────────"
