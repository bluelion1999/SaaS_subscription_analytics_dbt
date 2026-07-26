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
