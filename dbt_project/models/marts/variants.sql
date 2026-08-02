-- Canonical variants across all suppliers.
-- To add a supplier: add a union all branch pointing to its int_*_variants model.
select * from {{ ref('int_vta_variants') }}
{% if env_var('KES_BASE_URL', '') != '' %}
union all
select * from {{ ref('int_kes_variants') }}
{% endif %}
