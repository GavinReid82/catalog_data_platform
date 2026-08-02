select * from {{ ref('prices') }} where supplier = 'vta'
