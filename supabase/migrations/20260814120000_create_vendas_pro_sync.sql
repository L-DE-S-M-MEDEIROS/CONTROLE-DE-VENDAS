create schema if not exists private;

create table if not exists private.vendas_pro_authorized_users (
    user_id uuid primary key references auth.users(id) on delete cascade,
    email text not null unique,
    created_at timestamptz not null default now()
);

revoke all on private.vendas_pro_authorized_users from public, anon, authenticated;

insert into private.vendas_pro_authorized_users (user_id, email)
select id, lower(email)
from auth.users
where lower(email) = 'vendasldesmmedeiros@gmail.com'
on conflict (user_id) do update set email = excluded.email;

create or replace function public.vendas_pro_is_authorized()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from private.vendas_pro_authorized_users allowed
        where allowed.user_id = (select auth.uid())
          and allowed.email = lower(coalesce((select auth.jwt() ->> 'email'), ''))
    );
$$;

revoke all on function public.vendas_pro_is_authorized() from public, anon;
grant execute on function public.vendas_pro_is_authorized() to authenticated;

create table public.vendas_pro_products (
    id uuid primary key,
    owner_id uuid not null default auth.uid() references auth.users(id),
    name text not null check (length(btrim(name)) > 0),
    price_cents bigint not null check (price_cents >= 0),
    barcode text not null,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    unique (owner_id, barcode)
);

create table public.vendas_pro_clients (
    id uuid primary key,
    owner_id uuid not null default auth.uid() references auth.users(id),
    name text not null check (length(btrim(name)) > 0),
    notes text not null default '',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz
);

create unique index vendas_pro_clients_owner_name_unique
on public.vendas_pro_clients (owner_id, lower(name));

create table public.vendas_pro_sales (
    id uuid primary key,
    owner_id uuid not null default auth.uid() references auth.users(id),
    client_id uuid not null references public.vendas_pro_clients(id),
    sale_date date not null,
    total_cents bigint not null check (total_cents >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz
);

create table public.vendas_pro_sale_items (
    id uuid primary key,
    owner_id uuid not null default auth.uid() references auth.users(id),
    sale_id uuid not null references public.vendas_pro_sales(id) on delete cascade,
    product_id uuid not null references public.vendas_pro_products(id),
    product_name text not null,
    quantity integer not null check (quantity > 0),
    unit_price_cents bigint not null check (unit_price_cents >= 0),
    subtotal_cents bigint not null check (subtotal_cents >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index vendas_pro_sales_owner_date
on public.vendas_pro_sales (owner_id, sale_date);

create index vendas_pro_sale_items_sale
on public.vendas_pro_sale_items (sale_id);

create or replace function public.vendas_pro_touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger vendas_pro_products_touch_updated_at
before update on public.vendas_pro_products
for each row execute function public.vendas_pro_touch_updated_at();

create trigger vendas_pro_clients_touch_updated_at
before update on public.vendas_pro_clients
for each row execute function public.vendas_pro_touch_updated_at();

create trigger vendas_pro_sales_touch_updated_at
before update on public.vendas_pro_sales
for each row execute function public.vendas_pro_touch_updated_at();

create trigger vendas_pro_sale_items_touch_updated_at
before update on public.vendas_pro_sale_items
for each row execute function public.vendas_pro_touch_updated_at();

alter table public.vendas_pro_products enable row level security;
alter table public.vendas_pro_clients enable row level security;
alter table public.vendas_pro_sales enable row level security;
alter table public.vendas_pro_sale_items enable row level security;

create policy vendas_pro_products_select on public.vendas_pro_products
for select to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_products_insert on public.vendas_pro_products
for insert to authenticated
with check ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_products_update on public.vendas_pro_products
for update to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()))
with check ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_products_delete on public.vendas_pro_products
for delete to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));

create policy vendas_pro_clients_select on public.vendas_pro_clients
for select to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_clients_insert on public.vendas_pro_clients
for insert to authenticated
with check ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_clients_update on public.vendas_pro_clients
for update to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()))
with check ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_clients_delete on public.vendas_pro_clients
for delete to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));

create policy vendas_pro_sales_select on public.vendas_pro_sales
for select to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_sales_insert on public.vendas_pro_sales
for insert to authenticated
with check ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_sales_update on public.vendas_pro_sales
for update to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()))
with check ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_sales_delete on public.vendas_pro_sales
for delete to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));

create policy vendas_pro_sale_items_select on public.vendas_pro_sale_items
for select to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_sale_items_insert on public.vendas_pro_sale_items
for insert to authenticated
with check ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_sale_items_update on public.vendas_pro_sale_items
for update to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()))
with check ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));
create policy vendas_pro_sale_items_delete on public.vendas_pro_sale_items
for delete to authenticated
using ((select public.vendas_pro_is_authorized()) and owner_id = (select auth.uid()));

revoke all on public.vendas_pro_products from anon;
revoke all on public.vendas_pro_clients from anon;
revoke all on public.vendas_pro_sales from anon;
revoke all on public.vendas_pro_sale_items from anon;

grant select, insert, update, delete on public.vendas_pro_products to authenticated;
grant select, insert, update, delete on public.vendas_pro_clients to authenticated;
grant select, insert, update, delete on public.vendas_pro_sales to authenticated;
grant select, insert, update, delete on public.vendas_pro_sale_items to authenticated;

create or replace function public.vendas_pro_save_sale(
    sale_record jsonb,
    item_records jsonb
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
    target_sale_id uuid := (sale_record ->> 'id')::uuid;
    target_client_id uuid := (sale_record ->> 'client_id')::uuid;
    item jsonb;
    target_product_id uuid;
begin
    if not (select public.vendas_pro_is_authorized()) then
        raise exception 'Acesso não autorizado' using errcode = '42501';
    end if;

    if not exists (
        select 1 from public.vendas_pro_clients
        where id = target_client_id
          and owner_id = (select auth.uid())
          and deleted_at is null
    ) then
        raise exception 'Cliente remoto inválido' using errcode = '23503';
    end if;

    insert into public.vendas_pro_sales (
        id, owner_id, client_id, sale_date, total_cents, created_at, deleted_at
    ) values (
        target_sale_id,
        (select auth.uid()),
        target_client_id,
        (sale_record ->> 'sale_date')::date,
        (sale_record ->> 'total_cents')::bigint,
        coalesce((sale_record ->> 'created_at')::timestamptz, now()),
        null
    )
    on conflict (id) do update set
        client_id = excluded.client_id,
        sale_date = excluded.sale_date,
        total_cents = excluded.total_cents,
        deleted_at = null
    where vendas_pro_sales.owner_id = (select auth.uid());

    delete from public.vendas_pro_sale_items
    where sale_id = target_sale_id
      and owner_id = (select auth.uid());

    for item in select value from jsonb_array_elements(item_records)
    loop
        target_product_id := (item ->> 'product_id')::uuid;
        if not exists (
            select 1 from public.vendas_pro_products
            where id = target_product_id
              and owner_id = (select auth.uid())
              and deleted_at is null
        ) then
            raise exception 'Produto remoto inválido' using errcode = '23503';
        end if;

        insert into public.vendas_pro_sale_items (
            id, owner_id, sale_id, product_id, product_name,
            quantity, unit_price_cents, subtotal_cents
        ) values (
            (item ->> 'id')::uuid,
            (select auth.uid()),
            target_sale_id,
            target_product_id,
            item ->> 'product_name',
            (item ->> 'quantity')::integer,
            (item ->> 'unit_price_cents')::bigint,
            (item ->> 'subtotal_cents')::bigint
        );
    end loop;

    return target_sale_id;
end;
$$;

create or replace function public.vendas_pro_delete_sale(target_sale_id uuid)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
begin
    if not (select public.vendas_pro_is_authorized()) then
        raise exception 'Acesso não autorizado' using errcode = '42501';
    end if;

    update public.vendas_pro_sales
    set deleted_at = now()
    where id = target_sale_id
      and owner_id = (select auth.uid());

    delete from public.vendas_pro_sale_items
    where sale_id = target_sale_id
      and owner_id = (select auth.uid());
end;
$$;

revoke all on function public.vendas_pro_save_sale(jsonb, jsonb) from public, anon;
revoke all on function public.vendas_pro_delete_sale(uuid) from public, anon;
grant execute on function public.vendas_pro_save_sale(jsonb, jsonb) to authenticated;
grant execute on function public.vendas_pro_delete_sale(uuid) to authenticated;
