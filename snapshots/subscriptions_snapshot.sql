{% snapshot subscriptions_snapshot %}

{{
    config(
        unique_key = 'subscription_id',
        strategy = 'timestamp',
        updated_at = 'updated_at',
    )

}}

select * from {{ref('stg_orbit__subscriptions')}}

{% endsnapshot %}