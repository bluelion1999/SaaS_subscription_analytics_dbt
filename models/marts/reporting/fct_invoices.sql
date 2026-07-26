select
    invoices.invoice_id,
    invoices.subscription_id,
    subscriptions.plan_tier,
    subscriptions.status as subscription_status,
    invoices.invoice_date,
    invoices.status as invoice_status,
    invoices.amount,
    case when invoices.status = 'paid' then invoices.amount else 0 end as collected_amount,
    case when invoices.status = 'failed' then invoices.amount else 0 end as lost_amount,
    case when invoices.status = 'refunded' then invoices.amount else 0 end as refunded_amount

from {{ ref('stg_orbit__invoices') }} as invoices
inner join {{ ref('dim_subscriptions_current') }} as subscriptions
    on invoices.subscription_id = subscriptions.subscription_id
