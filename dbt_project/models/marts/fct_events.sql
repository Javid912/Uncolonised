-- =============================================================
-- fct_events
-- Layer: GOLD (Fact table)
-- Materialized: table
--
-- PURPOSE:
--   The canonical events table. One row per unique event.
--   Contains typed, clean, enriched data.
--   Foreign key concept: references district by name
--   (we use name rather than a numeric FK since the district list
--   is small and stable — keeps queries simple).
--
-- This is the table your API can query directly for most use cases.
-- For the public-facing API that needs tags pre-joined, use mart_events_api.
-- =============================================================

with enriched as (
    select * from {{ ref('int_events_enriched') }}
)

select
    -- Primary key
    raw_id                          as event_id,
    source_id,

    -- When
    event_date,
    time_start,
    time_end,

    -- Where
    postcode,
    district_name,
    street_address,

    -- What
    theme_clean                     as title,
    theme                           as description,
    event_type,
    has_route,
    route_text,
    is_recurring,
    recurrence_note,

    -- Search
    search_vector,

    -- Meta
    scraped_at

from enriched
