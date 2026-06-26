with staged as (
    select * from {{ ref('stg_posts') }}
)

select
    post_id,
    title,
    body_md,
    excerpt,
    author_name,
    slug,
    published,
    published_at,
    tags,

    setweight(
        to_tsvector('german_unaccent', unaccent(coalesce(title, ''))),
        'A'
    )
    ||
    setweight(
        to_tsvector('english_unaccent', unaccent(coalesce(title, ''))),
        'B'
    )
    ||
    setweight(
        to_tsvector('german_unaccent', unaccent(coalesce(body_md, ''))),
        'C'
    )
    ||
    setweight(
        to_tsvector('english_unaccent', unaccent(coalesce(body_md, ''))),
        'D'
    ) as search_vector,

    created_at,
    updated_at
from staged
where published = true
