with source as (

    select * from {{ source('orbit', 'raw_product_events') }}

),

renamed as (

    select
        event_id,
        user_id,
        event_type,
        event_timestamp::timestamp_ntz as event_timestamp

    from source

)

select * from renamed
