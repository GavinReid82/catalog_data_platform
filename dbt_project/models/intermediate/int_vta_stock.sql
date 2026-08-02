select
    'vta'       as supplier,
    product_ref,
    warehouse,
    stock_qty,
    available_date,
    in_stock_now

from {{ ref('stg_vta_stock') }}
