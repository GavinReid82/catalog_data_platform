-- Canonical print technique prices across all suppliers.
-- To add a supplier: add a union all branch pointing to its int_*_print_prices model.
select * from {{ ref('int_vta_print_prices') }}
{% if env_var('KES_BASE_URL', '') != '' %}
union all
select * from {{ ref('int_kes_print_prices') }}
{% endif %}
