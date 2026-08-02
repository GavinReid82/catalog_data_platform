select * from {{ ref('variants') }} where supplier = 'vta'
