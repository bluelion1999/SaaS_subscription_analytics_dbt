select
    subscriptions.subscription_id,
    subscriptions.user_id,
    users.user_name,
    users.email,
    users.country,
    subscriptions.plan_tier,
    subscriptions.status,
    subscriptions.mrr_amount,
    subscriptions.created_at,
    subscriptions.updated_at

from {{ ref('stg_orbit__subscriptions') }} as subscriptions
inner join {{ ref('stg_orbit__users') }} as users on subscriptions.user_id = users.user_id
