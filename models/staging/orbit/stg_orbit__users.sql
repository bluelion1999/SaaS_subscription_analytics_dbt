with source as (

    select * from {{ source('orbit', 'raw_users') }}

),

renamed as (

    select
        user_id,
        name as user_name,
        email,
        signup_date::date as signup_date,
        country

    from source

)

select * from renamed
