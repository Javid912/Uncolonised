-- =============================================================
-- stg_assemblies
-- Layer: STAGING (Silver)
-- Materialized: view
--
-- PURPOSE:
--   Take the raw strings from raw_assemblies and give them
--   proper types, clean nulls, and derive a few simple boolean flags.
--   Nothing clever happens here — just casting and tidying.
--
-- RULE: One row in = one row out. No filtering, no joining.
-- =============================================================

with source as (
    select * from {{ source('berlin_police', 'raw_assemblies') }}
),

cleaned as (
    select
        id                  as raw_id,
        source_id,
        scraped_at,

        -- ── Date and time ──────────────────────────────────────
        -- Raw format from the API: "24.04.2026" → DATE
        to_date(datum, 'DD.MM.YYYY')    as event_date,

        -- "10:00" → TIME. Handle empty strings gracefully.
        case
            when von ~ '^\d{2}:\d{2}$' then von::time
            else null
        end                             as time_start,

        case
            when bis ~ '^\d{2}:\d{2}$' then bis::time
            else null
        end                             as time_end,

        -- ── Location ───────────────────────────────────────────
        -- plz may be empty string from the API; normalize to null
        nullif(trim(plz), '')           as postcode,
        nullif(trim(strasse_nr), '')    as street_address,

        -- ── Content ────────────────────────────────────────────
        trim(thema)                     as theme,

        -- Route only exists for marches (Aufzüge), not vigils
        nullif(trim(aufzugsstrecke), '') as route_text,

        -- ── Derived flags ──────────────────────────────────────
        -- Has a route = it's a march, not a stationary assembly
        (aufzugsstrecke is not null and trim(aufzugsstrecke) <> '')
                                        as has_route,

        -- Recurring events mention patterns like:
        --   "täglich", "jeweils Mo., Di.", "every Wed."
        (
            thema ilike '%täglich%'
            or thema ilike '%jeweils%'
            or thema ilike '%daily%'
            or thema ilike '%every %'
            or thema ~ '\(vom \d{2}\.\d{2}\.'   -- "(vom DD.MM."
        )                               as is_recurring,

        -- Extract the recurrence note in parentheses if present
        -- e.g. "(vom 02.01. bis 26.06.2026 - jeweils Fr.)"
        (regexp_match(thema, '\(vom [^)]+\)'))[1]
                                        as recurrence_note,

        -- Strip the recurrence note from the theme for a cleaner title
        trim(regexp_replace(thema, '\s*\(vom [^)]+\)', '', 'g'))
                                        as theme_clean

    from source
    where datum is not null   -- skip any completely empty rows
)

select * from cleaned
