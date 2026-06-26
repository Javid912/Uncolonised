with posts as (
    select * from {{ ref('fct_posts') }}
)

select
    post_id,
    title,
    body_md,
    excerpt,
    author_name,
    slug,
    status,
    published_at,
    tags,
    search_vector,
    created_at,
    updated_at
from posts
order by published_at desc
