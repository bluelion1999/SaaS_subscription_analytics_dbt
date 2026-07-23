with source as (

    select * from {{ source('orbit', 'raw_subscriptions') }}

),

renamed as (

    select
        subscription_id,
        user_id,
        plan_tier,
        status,
        mrr_amount::numeric(10, 2) as mrr_amount,
        created_at::timestamp_ntz as created_at,
        updated_at::timestamp_ntz as updated_at

    from source

)

select * from renamed
