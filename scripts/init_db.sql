-- =============================================================
-- Uncolonised — Database Bootstrap
-- Runs automatically on first `docker compose up` via
-- docker-entrypoint-initdb.d. Safe to run multiple times.
-- =============================================================

-- ── Extensions ────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ── Translation synonym dictionary ────────────────────────────
CREATE TABLE IF NOT EXISTS search_translations (
    en_term     TEXT PRIMARY KEY,
    de_term     TEXT NOT NULL
);

TRUNCATE search_translations;

INSERT INTO search_translations (en_term, de_term) VALUES
('climate',      'Klima'),
('environment',  'Umwelt'),
('energy',       'Energie'),
('coal',         'Kohle'),
('solar',        'Solar'),
('housing',      'Wohnen'),
('rent',         'Miete'),
('eviction',     'Verdrängung'),
('tenant',       'Mieter'),
('strike',       'Streik'),
('union',        'Gewerkschaft'),
('wage',         'Lohn'),
('worker',       'Arbeitnehmer'),
('rights',       'Rechte'),
('freedom',      'Freiheit'),
('democracy',    'Demokratie'),
('peace',        'Frieden'),
('solidarity',   'Solidarität'),
('justice',      'Gerechtigkeit'),
('cycling',      'Fahrrad'),
('bicycle',      'Fahrrad'),
('transit',      'Verkehr'),
('march',        'Demonstration'),
('rally',        'Kundgebung'),
('protest',      'Protest'),
('vigil',        'Mahnwache'),
('refugee',      'Flüchtlinge'),
('asylum',       'Asyl'),
('police',       'Polizei'),
('women',        'Frauen'),
('war',          'Krieg'),
('weapons',      'Waffen'),

-- Anti-colonial / anti-imperialist focus terms
('colonial',     'Kolonial'),
('colonisation', 'Kolonisation'),
('imperialism',  'Imperialismus'),
('empire',       'Imperium'),
('occupation',   'Besatzung'),
('resistance',   'Widerstand'),
('liberation',   'Befreiung'),
('oppression',   'Unterdrückung'),
('indigenous',   'Indigen'),
('reparations',  'Reparationen'),
('decolonise',   'Dekolonisation'),
('apartheid',    'Apartheid'),
('genocide',     'Genozid'),
('sanctions',    'Sanktionen'),
('self-determination', 'Selbstbestimmung'),
('diaspora',     'Diaspora');

-- ── Custom text search configurations ─────────────────────────
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config WHERE cfgname = 'german_unaccent'
    ) THEN
        CREATE TEXT SEARCH CONFIGURATION german_unaccent (COPY = german);
        ALTER TEXT SEARCH CONFIGURATION german_unaccent
            ALTER MAPPING FOR hword, hword_part, word
            WITH unaccent, german_stem;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config WHERE cfgname = 'english_unaccent'
    ) THEN
        CREATE TEXT SEARCH CONFIGURATION english_unaccent (COPY = english);
        ALTER TEXT SEARCH CONFIGURATION english_unaccent
            ALTER MAPPING FOR hword, hword_part, word
            WITH unaccent, english_stem;
    END IF;
END $$;

-- ── Raw events table (Berlin Police source) ───────────────────
CREATE TABLE IF NOT EXISTS raw_assemblies (
    id              BIGSERIAL PRIMARY KEY,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_id       INTEGER     NOT NULL,
    datum           TEXT,
    von             TEXT,
    bis             TEXT,
    thema           TEXT,
    plz             TEXT,
    strasse_nr      TEXT,
    aufzugsstrecke  TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS raw_assemblies_source_id_datum_uq
    ON raw_assemblies (source_id, datum);

CREATE INDEX IF NOT EXISTS raw_assemblies_scraped_at_idx
    ON raw_assemblies (scraped_at);

-- ── Blog posts table ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_posts (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    title           TEXT NOT NULL,
    body_md         TEXT NOT NULL,
    excerpt         TEXT,
    author_name     TEXT NOT NULL,
    slug            TEXT UNIQUE NOT NULL,
    published       BOOLEAN NOT NULL DEFAULT false,
    published_at    TIMESTAMPTZ,
    tags            TEXT[] DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS raw_posts_published_at_idx
    ON raw_posts (published_at DESC);

CREATE INDEX IF NOT EXISTS raw_posts_tags_idx
    ON raw_posts USING GIN (tags);

-- ── User submissions table (event tips / article ideas) ──────
CREATE TABLE IF NOT EXISTS submissions (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    submission_type TEXT NOT NULL CHECK (submission_type IN ('event', 'post', 'tip')),
    title           TEXT NOT NULL,
    description     TEXT,
    contact_name    TEXT,
    contact_email   TEXT,
    event_date      DATE,
    event_location  TEXT,
    tags            TEXT[] DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'needs_review')),
    reviewed_by     TEXT,
    reviewed_at     TIMESTAMPTZ,
    notes           TEXT
);