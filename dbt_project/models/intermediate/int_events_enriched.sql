-- =============================================================
-- int_events_enriched
-- Layer: INTERMEDIATE (Silver)
-- Materialized: view
--
-- PURPOSE:
--   Add meaning to the cleaned staging data:
--     1. Map postcode → district (Bezirk) name
--     2. Classify event type (vigil / march / rally / sit-in / other)
--     3. Build the PostgreSQL full-text search vector (German stemmer)
--
-- This is where domain knowledge lives.
-- Tag matching happens in a separate model (int_event_tags).
-- =============================================================

-- =============================================================
-- int_events_enriched
-- Layer: INTERMEDIATE (Silver)
-- Materialized: view
--
-- Changes from v1:
--   - search_vector now combines German + English stemming with weights
--   - unaccent applied so "Buro" finds "Büro"
--   - title (weight A) ranked higher than description (weight B)
-- =============================================================
-- =============================================================
-- int_events_enriched
-- Layer: INTERMEDIATE (Silver)
-- Materialized: view
--
-- Changes from v1:
--   - search_vector now combines German + English stemming with weights
--   - unaccent applied so "Buro" finds "Büro"
--   - title (weight A) ranked higher than description (weight B)
-- =============================================================

with staged as (
    select * from {{ ref('stg_assemblies') }}
),

with_district as (
    select
        staged.*,

        case
            when postcode between '10115' and '10179' then 'Mitte'
            when postcode between '10243' and '10249' then 'Friedrichshain-Kreuzberg'
            when postcode between '10961' and '10999' then 'Friedrichshain-Kreuzberg'
            when postcode between '10405' and '10439' then 'Pankow'
            when postcode between '10551' and '10589' then 'Mitte'
            when postcode between '10623' and '10629' then 'Charlottenburg-Wilmersdorf'
            when postcode between '10707' and '10719' then 'Charlottenburg-Wilmersdorf'
            when postcode between '10781' and '10789' then 'Tempelhof-Schöneberg'
            when postcode between '10823' and '10829' then 'Tempelhof-Schöneberg'
            when postcode between '12043' and '12059' then 'Neukölln'
            when postcode between '12099' and '12109' then 'Tempelhof-Schöneberg'
            when postcode between '12157' and '12169' then 'Steglitz-Zehlendorf'
            when postcode between '12203' and '12209' then 'Steglitz-Zehlendorf'
            when postcode between '12247' and '12279' then 'Steglitz-Zehlendorf'
            when postcode between '12305' and '12309' then 'Tempelhof-Schöneberg'
            when postcode between '12347' and '12359' then 'Neukölln'
            when postcode between '12435' and '12439' then 'Treptow-Köpenick'
            when postcode between '12459' and '12529' then 'Treptow-Köpenick'
            when postcode between '12555' and '12559' then 'Treptow-Köpenick'
            when postcode between '12587' and '12589' then 'Treptow-Köpenick'
            when postcode between '12619' and '12629' then 'Marzahn-Hellersdorf'
            when postcode between '12679' and '12689' then 'Marzahn-Hellersdorf'
            when postcode between '12681' and '12685' then 'Marzahn-Hellersdorf'
            when postcode between '13051' and '13059' then 'Lichtenberg'
            when postcode between '13086' and '13088' then 'Pankow'
            when postcode between '13125' and '13129' then 'Pankow'
            when postcode between '13156' and '13158' then 'Pankow'
            when postcode between '13187' and '13189' then 'Pankow'
            when postcode between '13347' and '13359' then 'Mitte'
            when postcode between '13403' and '13409' then 'Reinickendorf'
            when postcode between '13435' and '13439' then 'Reinickendorf'
            when postcode between '13465' and '13469' then 'Reinickendorf'
            when postcode between '13503' and '13509' then 'Spandau'
            when postcode between '13581' and '13599' then 'Spandau'
            when postcode between '13627' and '13629' then 'Spandau'
            when postcode between '14050' and '14059' then 'Charlottenburg-Wilmersdorf'
            when postcode between '14163' and '14169' then 'Steglitz-Zehlendorf'
            when postcode between '14193' and '14199' then 'Charlottenburg-Wilmersdorf'
            else 'Unknown'
        end as district_name,

        case
            when has_route = true                                         then 'march'
            when theme_clean ilike '%Mahnwache%'
              or theme_clean ilike '%Vigil%'
              or theme_clean ilike '%Dauermahnwache%'                     then 'vigil'
            when theme_clean ilike '%Sitzblockade%'
              or theme_clean ilike '%Sit-in%'
              or theme_clean ilike '%Sitzkundgebung%'                     then 'sit-in'
            when theme_clean ilike '%Streikposten%'
              or theme_clean ilike '%Streik%'                             then 'strike'
            when theme_clean ilike '%Kundgebung%'
              or theme_clean ilike '%Demonstration%'
              or theme_clean ilike '%Demo%'                               then 'rally'
            when theme_clean ilike '%Fahrrad%'
              or theme_clean ilike '%Critical Mass%'                      then 'cycling'
            else 'assembly'
        end as event_type,

        -- ── Rich search vector (the key improvement) ──────────
        --
        -- We combine FOUR weighted vectors:
        --
        --   Weight A (highest): title in German  — exact topic match
        --   Weight B          : title in English  — "climate", "housing", "rights"
        --   Weight C          : description in German
        --   Weight D (lowest) : description in English
        --
        -- unaccent() means "Buro" finds "Büro", "Gaza" finds "GAZA"
        -- German stemmer handles German morphology
        -- English stemmer handles English phrases common in Berlin demos:
        --   "Fridays for Future", "Stand with Ukraine", "Black Lives Matter",
        --   "Critical Mass", "Pride", "solidarity"
        --
        setweight(
            to_tsvector('german_unaccent', unaccent(coalesce(theme_clean, ''))),
            'A'
        )
        ||
        setweight(
            to_tsvector('english_unaccent', unaccent(coalesce(theme_clean, ''))),
            'B'
        )
        ||
        setweight(
            to_tsvector('german_unaccent', unaccent(coalesce(theme, ''))),
            'C'
        )
        ||
        setweight(
            to_tsvector('english_unaccent', unaccent(coalesce(theme, ''))),
            'D'
        )
        as search_vector

    from staged
)

select * from with_district