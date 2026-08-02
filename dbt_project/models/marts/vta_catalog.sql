select * from {{ ref('catalog') }} where supplier = 'vta'
