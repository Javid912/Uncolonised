-- =============================================================
-- mart_events_api
-- Layer: GOLD (Mart)
-- Materialized: table (with indexes, see dbt_project.yml)
--
-- PURPOSE:
--   The table your API actually queries.
--   It pre-joins events + tags so the API never needs to do
--   a runtime JOIN — just filter and return.
--
--   Tags are aggregated into a JSONB array per event:
--     [{"slug": "climate", "label_de": "Klima & Umwelt"}, ...]
--
--   API query for "all housing demos after today, sorted by date":
--     SELECT * FROM mart_events_api
--     WHERE event_date >= CURRENT_DATE
--       AND tags @> '[{"slug": "housing"}]'  -- JSONB containment
--     ORDER BY event_date, time_start;
--
--   API query for full-text search "Miete Kreuzberg":
--     SELECT * FROM mart_events_api
--     WHERE search_vector @@ plainto_tsquery('german', 'Miete Kreuzberg');
-- =============================================================

with events as (
    select * from {{ ref('fct_events') }}
),

tags_aggregated as (
    -- Collapse all tags for each event into one JSONB array
    select
        event_id,
        jsonb_agg(
            jsonb_build_object(
                'slug',     slug,
                'label_de', label_de,
                'label_en', label_en
            )
            order by slug  -- consistent ordering
        ) as tags
    from {{ ref('bridge_event_tags') }}
    group by event_id
)

select
    -- Core identifiers
    e.event_id,
    e.source_id,

    -- When
    e.event_date,
    e.time_start,
    e.time_end,

    -- Where (everything the map needs)
    e.postcode,
    e.district_name,
    e.street_address,

    -- What
    e.title,
    e.description,
    e.event_type,
    e.has_route,
    e.route_text,
    e.is_recurring,
    e.recurrence_note,

    -- Tags as JSONB — the API returns this directly to the frontend
    coalesce(t.tags, '[]'::jsonb)   as tags,

    -- Search (indexed with GIN)
    e.search_vector,

    -- Meta
    e.scraped_at

from events e
left join tags_aggregated t
    on e.event_id = t.event_id
