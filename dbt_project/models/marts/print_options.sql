-- Canonical print options across all suppliers.
-- To add a supplier: add a union all branch pointing to its int_*_print_options model.
select * from {{ ref('int_vta_print_options') }}
{% if env_var('KES_BASE_URL', '') != '' %}
union all
select * from {{ ref('int_kes_print_options') }}
{% endif %}
