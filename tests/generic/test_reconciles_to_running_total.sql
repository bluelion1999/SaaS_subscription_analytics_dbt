{% test reconciles_to_running_total(model, column_name, delta_column, partition_by, order_by) %}

with validation as (
    select  
        {{partition_by}} as partition_key,
        {{column_name}} as balance,
        SUM({{delta_column}}) OVER (partition by {{partition_by}} order by {{order_by}}) as running_total
    from
        {{model}}
)

select *
from validation
where running_total != balance

{% endtest %}