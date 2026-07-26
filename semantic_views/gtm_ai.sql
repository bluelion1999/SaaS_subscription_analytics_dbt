-- NOT dbt-managed, so unlike the marts it queries, grants here don't
-- auto-reconcile on rebuild. CREATE OR REPLACE drops them just like a
-- table would -- re-run this after every change:
--   grant select on semantic view orbit_analytics.marts.gtm_ai to role svc_gtm_ai_role;
create or replace semantic view orbit_analytics.marts.gtm_ai
  tables (
    movements as orbit_analytics.marts.subscription_mrr_movements
      primary key (subscription_id, effective_date),
    subscriptions as orbit_analytics.marts.dim_subscriptions_current
      primary key (subscription_id),
    engagement as orbit_analytics.marts.subscription_engagement_summary
      primary key (subscription_id),
    invoices as orbit_analytics.marts.fct_invoices
      primary key (invoice_id)
  )
  relationships (
    movements_to_subscriptions as movements (subscription_id) references subscriptions,
    engagement_to_subscriptions as engagement (subscription_id) references subscriptions,
    invoices_to_subscriptions as invoices (subscription_id) references subscriptions
  )
  dimensions (
    movements.movement_type as movement_type,
    subscriptions.status as status,
    subscriptions.plan_tier as plan_tier,
    subscriptions.country as country,
    movements.effective_date as effective_date,
    invoices.invoice_status as invoice_status
  )
  metrics (
    movements.net_mrr_movement as sum(mrr_delta),
    movements.movement_count as count(*),
    subscriptions.total_mrr as sum(mrr_amount),
    subscriptions.subscription_count as count(*),
    engagement.total_events as sum(total_events),
    engagement.avg_active_days as avg(distinct_active_days),
    engagement.avg_days_since_last_event as avg(days_since_last_event),
    invoices.invoice_count as count(*),
    invoices.collected_revenue as sum(collected_amount),
    invoices.lost_revenue as sum(lost_amount),
    invoices.refunded_revenue as sum(refunded_amount)
  )
  ai_verified_queries (
    churned_mrr as (
      question 'What was total churned MRR?'
      verified_at 1785099365
      onboarding_question true
      sql 'select net_mrr_movement from semantic_view(orbit_analytics.marts.gtm_ai metrics movements.net_mrr_movement dimensions movements.movement_type) where movement_type = ''churn'''
    ),
    active_enterprise_subscriptions as (
      question 'How many active enterprise subscriptions are there?'
      verified_at 1785099365
      onboarding_question true
      sql 'select subscription_count from semantic_view(orbit_analytics.marts.gtm_ai metrics subscriptions.subscription_count dimensions subscriptions.status, subscriptions.plan_tier) where status = ''active'' and plan_tier = ''enterprise'''
    ),
    revenue_collected_vs_lost as (
      question 'How much revenue was collected versus lost to failed payments?'
      verified_at 1785099365
      onboarding_question true
      sql 'select collected_revenue, lost_revenue from semantic_view(orbit_analytics.marts.gtm_ai metrics invoices.collected_revenue, invoices.lost_revenue)'
    ),
    engagement_by_status as (
      question 'What is average days since last activity for active subscriptions?'
      verified_at 1785099365
      onboarding_question true
      sql 'select avg_days_since_last_event from semantic_view(orbit_analytics.marts.gtm_ai metrics engagement.avg_days_since_last_event dimensions subscriptions.status) where status = ''active'''
    )
  )
