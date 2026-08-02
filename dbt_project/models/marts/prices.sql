-- Canonical price tiers across all suppliers.
-- To add a supplier: add a union all branch pointing to its int_*_prices model.
select * from {{ ref('int_vta_prices') }}
{% if env_var('KES_BASE_URL', '') != '' %}
union all
select * from {{ ref('int_kes_prices') }}
{% endif %}
