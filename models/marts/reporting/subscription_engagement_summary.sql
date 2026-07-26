select
    events.user_id as subscription_id,
    count(*) as total_events,
    count(distinct date(events.event_timestamp)) as distinct_active_days,
    max(events.event_timestamp) as last_event_at,
    datediff('day', max(events.event_timestamp), current_timestamp()) as days_since_last_event

from {{ ref('fct_product_events') }} as events
group by events.user_id
