-- =============================================================
-- bridge_event_tags
-- Layer: GOLD
-- Materialized: table
--
-- PURPOSE:
--   Resolves the many-to-many relationship between events and tags.
--   One row per (event, tag) pair.
--
--   Why a bridge table?
--   One event can have many tags (climate + housing + labor).
--   One tag applies to many events.
--   You cannot store this in fct_events without arrays,
--   which break simple SQL filtering.
--
--   To find all climate events:
--     SELECT * FROM fct_events
--     JOIN bridge_event_tags USING (event_id)
--     WHERE slug = 'climate';
-- =============================================================

select
    raw_id      as event_id,
    source_id,
    event_date,
    slug,
    label_de,
    label_en
from {{ ref('int_event_tags') }}
