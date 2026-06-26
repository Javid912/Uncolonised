with source as (
    select * from {{ source('uncolonised', 'raw_posts') }}
),

cleaned as (
    select
        id                          as post_id,
        title,
        body_md,
        coalesce(excerpt, left(body_md, 200)) as excerpt,
        author_name,
        slug,
        published,
        published_at,
        tags,
        created_at,
        updated_at
    from source
    where title is not null
      and body_md is not null
)

select * from cleaned
