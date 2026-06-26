FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper/ ./scraper/
COPY dbt_project/ ./dbt_project/
COPY scripts/ ./scripts/

RUN chmod +x ./scripts/pipeline_run.sh

ENV DBT_PROFILES_DIR=/app/dbt_project
