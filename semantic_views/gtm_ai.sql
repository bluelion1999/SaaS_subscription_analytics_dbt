create or replace semantic view orbit_analytics.marts.gtm_ai
  tables (
    movements as orbit_analytics.marts.subscription_mrr_movements
      primary key (subscription_id, effective_date),
    subscriptions as orbit_analytics.marts.dim_subscriptions_current
      primary key (subscription_id)
  )
  relationships (
    movements_to_subscriptions as movements (subscription_id) references subscriptions
  )
  dimensions (
    movements.movement_type as movement_type,
    subscriptions.status as status,
    subscriptions.plan_tier as plan_tier,
    subscriptions.country as country,
    movements.effective_date as effective_date
  )
  metrics (
    movements.net_mrr_movement as sum(mrr_delta),
    movements.movement_count as count(*),
    subscriptions.total_mrr as sum(mrr_amount),
    subscriptions.subscription_count as count(*)
  )
