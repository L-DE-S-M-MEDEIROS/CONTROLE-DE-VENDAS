create index if not exists vendas_pro_sales_client
on public.vendas_pro_sales (client_id);

create index if not exists vendas_pro_sale_items_owner
on public.vendas_pro_sale_items (owner_id);

create index if not exists vendas_pro_sale_items_product
on public.vendas_pro_sale_items (product_id);
