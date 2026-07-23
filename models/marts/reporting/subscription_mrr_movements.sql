with subscription_history as (
    select
        subscription_id,
        status,
        mrr_amount,
        dbt_valid_from as effective_date,
        lag(status) over (partition by subscription_id order by dbt_valid_from) as previous_status,
        lag(mrr_amount) over (partition by subscription_id order by dbt_valid_from) as previous_mrr_amount
    from
        {{ref('subscriptions_snapshot')}}
)

select
    subscription_id,
    effective_date,
    previous_status,
    status as current_status,
    previous_mrr_amount,
    mrr_amount as current_mrr_amount,
    mrr_amount - coalesce(previous_mrr_amount,0) as mrr_delta,
    case
        when previous_status IS NULL THEN 'new'
        when previous_status = 'trial' and status = 'active' THEN 'new'
        when previous_status IN ('canceled','past_due') AND status = 'active' THEN 'reactivation'
        when previous_status = 'active' AND status ='active' AND mrr_delta > 0 THEN 'expansion'
        when previous_status = 'active' AND status = 'active' AND mrr_delta < 0 THEN 'contraction'
        when previous_status = 'active' AND status ='past_due' THEN 'at_risk'
        when previous_status = 'active' AND status = 'canceled' THEN 'churn'
        when previous_status = 'past_due' AND status = 'canceled' THEN 'churn'
        else 'no_change'
    end as movement_type
from
    subscription_history