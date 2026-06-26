-- =============================================================
-- int_event_tags
-- Layer: INTERMEDIATE (Silver)
-- Materialized: view
--
-- PURPOSE:
--   Match each event's theme text against the tag_rules seed file.
--   Produces one row per (event, matching_tag) pair.
--
-- HOW IT WORKS:
--   The seed file has a "pattern" column with pipe-separated keywords,
--   e.g. "Miete|Wohnen|Verdrängung".
--   We use a CROSS JOIN to test every event against every tag rule,
--   then keep only the matches.
--   Updating your tags = edit seeds/tag_rules.csv, run `dbt seed`,
--   then `dbt run`. No code changes needed.
--
-- OUTPUT: (raw_id, source_id, event_date, slug, label_de, label_en)
-- =============================================================

with events as (
    select
        raw_id,
        source_id,
        event_date,
        theme_clean
    from {{ ref('int_events_enriched') }}
),

tag_rules as (
    select
        slug,
        label_de,
        label_en,
        pattern   -- pipe-separated regex alternation, e.g. "Miete|Wohnen"
    from {{ ref('tag_rules') }}
),

matched as (
    select
        e.raw_id,
        e.source_id,
        e.event_date,
        t.slug,
        t.label_de,
        t.label_en
    from events e
    -- CROSS JOIN: test every event against every tag rule
    cross join tag_rules t
    -- Case-insensitive regex match of the theme against the pattern
    where e.theme_clean ~* t.pattern
)

select * from matched
