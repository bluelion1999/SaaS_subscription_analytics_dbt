with source as (

    select * from {{ source('orbit', 'raw_invoices') }}

),

renamed as (

    select
        invoice_id,
        subscription_id,
        amount::numeric(10, 2) as amount,
        invoice_date::date as invoice_date,
        status

    from source

)

select * from renamed
