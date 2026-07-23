{{
    config(
        materialized='incremental',
        unique_key = 'event_id',
        incremental_strategy = 'merge'
)
}}

select * from {{ref('stg_orbit__product_events')}}

{% if is_incremental() %}
where event_timestamp > (select coalesce(max(event_timestamp),  '1900-01-01') from {{ this }} )
{% endif %}
