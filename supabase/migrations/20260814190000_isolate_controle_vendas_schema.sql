create schema if not exists controle_vendas;

revoke all on schema controle_vendas from public, anon;
grant usage on schema controle_vendas to authenticated;

create table controle_vendas.authorized_users (
    user_id uuid primary key references auth.users(id) on delete cascade,
    email text not null unique,
    created_at timestamptz not null default now()
);

alter table controle_vendas.authorized_users enable row level security;
revoke all on controle_vendas.authorized_users from public, anon, authenticated;

insert into controle_vendas.authorized_users (user_id, email)
select id, lower(email)
from auth.users
where lower(email) = 'vendasldesmmedeiros@gmail.com'
on conflict (user_id) do update set email = excluded.email;

create or replace function controle_vendas.is_authorized()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from controle_vendas.authorized_users allowed
        where allowed.user_id = (select auth.uid())
          and allowed.email = lower(coalesce((select auth.jwt() ->> 'email'), ''))
    );
$$;

revoke all on function controle_vendas.is_authorized() from public, anon;
grant execute on function controle_vendas.is_authorized() to authenticated;

create table controle_vendas.products (
    id uuid primary key,
    owner_id uuid not null default auth.uid() references auth.users(id),
    name text not null check (length(btrim(name)) > 0),
    price_cents bigint not null check (price_cents >= 0),
    barcode text not null,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    revision bigint not null default 1 check (revision > 0),
    unique (owner_id, barcode)
);

create table controle_vendas.clients (
    id uuid primary key,
    owner_id uuid not null default auth.uid() references auth.users(id),
    name text not null check (length(btrim(name)) > 0),
    notes text not null default '',
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    revision bigint not null default 1 check (revision > 0)
);

create unique index controle_vendas_clients_owner_name_unique
on controle_vendas.clients (owner_id, lower(name));

create table controle_vendas.sales (
    id uuid primary key,
    owner_id uuid not null default auth.uid() references auth.users(id),
    client_id uuid not null references controle_vendas.clients(id),
    sale_date date not null,
    total_cents bigint not null check (total_cents >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz,
    revision bigint not null default 1 check (revision > 0)
);

create table controle_vendas.sale_items (
    id uuid primary key,
    owner_id uuid not null default auth.uid() references auth.users(id),
    sale_id uuid not null references controle_vendas.sales(id) on delete cascade,
    product_id uuid not null references controle_vendas.products(id),
    product_name text not null,
    quantity integer not null check (quantity > 0),
    unit_price_cents bigint not null check (unit_price_cents >= 0),
    subtotal_cents bigint not null check (subtotal_cents >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    revision bigint not null default 1 check (revision > 0)
);

create index controle_vendas_sales_owner_date
on controle_vendas.sales (owner_id, sale_date);
create index controle_vendas_sales_client
on controle_vendas.sales (client_id);
create index controle_vendas_sale_items_sale
on controle_vendas.sale_items (sale_id);
create index controle_vendas_sale_items_owner
on controle_vendas.sale_items (owner_id);
create index controle_vendas_sale_items_product
on controle_vendas.sale_items (product_id);

create or replace function controle_vendas.touch_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger controle_vendas_products_touch_updated_at
before update on controle_vendas.products
for each row execute function controle_vendas.touch_updated_at();
create trigger controle_vendas_clients_touch_updated_at
before update on controle_vendas.clients
for each row execute function controle_vendas.touch_updated_at();
create trigger controle_vendas_sales_touch_updated_at
before update on controle_vendas.sales
for each row execute function controle_vendas.touch_updated_at();

alter table controle_vendas.products enable row level security;
alter table controle_vendas.clients enable row level security;
alter table controle_vendas.sales enable row level security;
alter table controle_vendas.sale_items enable row level security;

revoke all on controle_vendas.products from public, anon, authenticated;
revoke all on controle_vendas.clients from public, anon, authenticated;
revoke all on controle_vendas.sales from public, anon, authenticated;
revoke all on controle_vendas.sale_items from public, anon, authenticated;
grant select, insert, update, delete on controle_vendas.products to authenticated;
grant select, insert, update, delete on controle_vendas.clients to authenticated;
grant select, insert, update, delete on controle_vendas.sales to authenticated;
grant select, insert, update, delete on controle_vendas.sale_items to authenticated;

create policy controle_vendas_products_select on controle_vendas.products
for select to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_products_insert on controle_vendas.products
for insert to authenticated
with check ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_products_update on controle_vendas.products
for update to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()))
with check ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_products_delete on controle_vendas.products
for delete to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));

create policy controle_vendas_clients_select on controle_vendas.clients
for select to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_clients_insert on controle_vendas.clients
for insert to authenticated
with check ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_clients_update on controle_vendas.clients
for update to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()))
with check ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_clients_delete on controle_vendas.clients
for delete to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));

create policy controle_vendas_sales_select on controle_vendas.sales
for select to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_sales_insert on controle_vendas.sales
for insert to authenticated
with check ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_sales_update on controle_vendas.sales
for update to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()))
with check ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_sales_delete on controle_vendas.sales
for delete to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));

create policy controle_vendas_sale_items_select on controle_vendas.sale_items
for select to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_sale_items_insert on controle_vendas.sale_items
for insert to authenticated
with check ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_sale_items_update on controle_vendas.sale_items
for update to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()))
with check ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));
create policy controle_vendas_sale_items_delete on controle_vendas.sale_items
for delete to authenticated
using ((select controle_vendas.is_authorized()) and owner_id = (select auth.uid()));

insert into controle_vendas.products
select id, owner_id, name, price_cents, barcode, active,
       created_at, updated_at, deleted_at, revision
from public.vendas_pro_products
on conflict (id) do nothing;

insert into controle_vendas.clients
select id, owner_id, name, notes, active,
       created_at, updated_at, deleted_at, revision
from public.vendas_pro_clients
on conflict (id) do nothing;

insert into controle_vendas.sales
select id, owner_id, client_id, sale_date, total_cents,
       created_at, updated_at, deleted_at, revision
from public.vendas_pro_sales
on conflict (id) do nothing;

insert into controle_vendas.sale_items
select id, owner_id, sale_id, product_id, product_name, quantity,
       unit_price_cents, subtotal_cents, created_at, updated_at, revision
from public.vendas_pro_sale_items
on conflict (id) do nothing;

create or replace function public.controle_vendas_save_product(product_record jsonb)
returns bigint
language plpgsql
security invoker
set search_path = ''
as $$
declare
    target_id uuid := (product_record ->> 'id')::uuid;
    expected bigint := coalesce((product_record ->> 'expected_revision')::bigint, 0);
    new_revision bigint;
begin
    if not (select controle_vendas.is_authorized()) then
        raise exception 'Acesso não autorizado' using errcode = '42501';
    end if;
    if exists (
        select 1 from controle_vendas.products
        where id = target_id and owner_id = (select auth.uid())
    ) then
        update controle_vendas.products set
            name = product_record ->> 'name',
            price_cents = (product_record ->> 'price_cents')::bigint,
            barcode = product_record ->> 'barcode',
            active = (product_record ->> 'active')::boolean,
            deleted_at = (product_record ->> 'deleted_at')::timestamptz,
            revision = revision + 1
        where id = target_id
          and owner_id = (select auth.uid())
          and revision = expected
        returning revision into new_revision;
        if new_revision is null then
            raise exception 'VENDAS_PRO_CONFLICT:product' using errcode = '40001';
        end if;
    else
        if expected <> 0 then
            raise exception 'VENDAS_PRO_CONFLICT:product' using errcode = '40001';
        end if;
        insert into controle_vendas.products (
            id, owner_id, name, price_cents, barcode, active,
            created_at, deleted_at, revision
        ) values (
            target_id, (select auth.uid()), product_record ->> 'name',
            (product_record ->> 'price_cents')::bigint,
            product_record ->> 'barcode',
            (product_record ->> 'active')::boolean,
            coalesce((product_record ->> 'created_at')::timestamptz, now()),
            (product_record ->> 'deleted_at')::timestamptz, 1
        ) returning revision into new_revision;
    end if;
    return new_revision;
end;
$$;

create or replace function public.controle_vendas_save_client(client_record jsonb)
returns bigint
language plpgsql
security invoker
set search_path = ''
as $$
declare
    target_id uuid := (client_record ->> 'id')::uuid;
    expected bigint := coalesce((client_record ->> 'expected_revision')::bigint, 0);
    new_revision bigint;
begin
    if not (select controle_vendas.is_authorized()) then
        raise exception 'Acesso não autorizado' using errcode = '42501';
    end if;
    if exists (
        select 1 from controle_vendas.clients
        where id = target_id and owner_id = (select auth.uid())
    ) then
        update controle_vendas.clients set
            name = client_record ->> 'name',
            notes = coalesce(client_record ->> 'notes', ''),
            active = (client_record ->> 'active')::boolean,
            deleted_at = (client_record ->> 'deleted_at')::timestamptz,
            revision = revision + 1
        where id = target_id
          and owner_id = (select auth.uid())
          and revision = expected
        returning revision into new_revision;
        if new_revision is null then
            raise exception 'VENDAS_PRO_CONFLICT:client' using errcode = '40001';
        end if;
    else
        if expected <> 0 then
            raise exception 'VENDAS_PRO_CONFLICT:client' using errcode = '40001';
        end if;
        insert into controle_vendas.clients (
            id, owner_id, name, notes, active, created_at, deleted_at, revision
        ) values (
            target_id, (select auth.uid()), client_record ->> 'name',
            coalesce(client_record ->> 'notes', ''),
            (client_record ->> 'active')::boolean,
            coalesce((client_record ->> 'created_at')::timestamptz, now()),
            (client_record ->> 'deleted_at')::timestamptz, 1
        ) returning revision into new_revision;
    end if;
    return new_revision;
end;
$$;

create or replace function public.controle_vendas_save_sale(
    sale_record jsonb,
    item_records jsonb,
    expected_revision bigint
)
returns bigint
language plpgsql
security invoker
set search_path = ''
as $$
declare
    target_sale_id uuid := (sale_record ->> 'id')::uuid;
    target_client_id uuid := (sale_record ->> 'client_id')::uuid;
    item jsonb;
    target_product_id uuid;
    new_revision bigint;
begin
    if not (select controle_vendas.is_authorized()) then
        raise exception 'Acesso não autorizado' using errcode = '42501';
    end if;
    if not exists (
        select 1 from controle_vendas.clients
        where id = target_client_id
          and owner_id = (select auth.uid())
          and deleted_at is null
    ) then
        raise exception 'Cliente remoto inválido' using errcode = '23503';
    end if;
    if exists (
        select 1 from controle_vendas.sales
        where id = target_sale_id and owner_id = (select auth.uid())
    ) then
        update controle_vendas.sales set
            client_id = target_client_id,
            sale_date = (sale_record ->> 'sale_date')::date,
            total_cents = (sale_record ->> 'total_cents')::bigint,
            deleted_at = null,
            revision = revision + 1
        where id = target_sale_id
          and owner_id = (select auth.uid())
          and revision = expected_revision
        returning revision into new_revision;
        if new_revision is null then
            raise exception 'VENDAS_PRO_CONFLICT:sale' using errcode = '40001';
        end if;
    else
        if expected_revision <> 0 then
            raise exception 'VENDAS_PRO_CONFLICT:sale' using errcode = '40001';
        end if;
        insert into controle_vendas.sales (
            id, owner_id, client_id, sale_date, total_cents, created_at, revision
        ) values (
            target_sale_id, (select auth.uid()), target_client_id,
            (sale_record ->> 'sale_date')::date,
            (sale_record ->> 'total_cents')::bigint,
            coalesce((sale_record ->> 'created_at')::timestamptz, now()), 1
        ) returning revision into new_revision;
    end if;
    delete from controle_vendas.sale_items
    where sale_id = target_sale_id and owner_id = (select auth.uid());
    for item in select value from jsonb_array_elements(item_records)
    loop
        target_product_id := (item ->> 'product_id')::uuid;
        if not exists (
            select 1 from controle_vendas.products
            where id = target_product_id
              and owner_id = (select auth.uid())
              and deleted_at is null
        ) then
            raise exception 'Produto remoto inválido' using errcode = '23503';
        end if;
        insert into controle_vendas.sale_items (
            id, owner_id, sale_id, product_id, product_name,
            quantity, unit_price_cents, subtotal_cents
        ) values (
            (item ->> 'id')::uuid, (select auth.uid()), target_sale_id,
            target_product_id, item ->> 'product_name',
            (item ->> 'quantity')::integer,
            (item ->> 'unit_price_cents')::bigint,
            (item ->> 'subtotal_cents')::bigint
        );
    end loop;
    return new_revision;
end;
$$;

create or replace function public.controle_vendas_delete_sale(
    target_sale_id uuid,
    expected_revision bigint
)
returns bigint
language plpgsql
security invoker
set search_path = ''
as $$
declare
    new_revision bigint;
begin
    if not (select controle_vendas.is_authorized()) then
        raise exception 'Acesso não autorizado' using errcode = '42501';
    end if;
    update controle_vendas.sales
    set deleted_at = now(), revision = revision + 1
    where id = target_sale_id
      and owner_id = (select auth.uid())
      and revision = expected_revision
    returning revision into new_revision;
    if new_revision is null then
        raise exception 'VENDAS_PRO_CONFLICT:sale' using errcode = '40001';
    end if;
    delete from controle_vendas.sale_items
    where sale_id = target_sale_id and owner_id = (select auth.uid());
    return new_revision;
end;
$$;

create or replace function public.controle_vendas_snapshot()
returns jsonb
language plpgsql
stable
security invoker
set search_path = ''
as $$
begin
    if not (select controle_vendas.is_authorized()) then
        raise exception 'Acesso não autorizado' using errcode = '42501';
    end if;
    return jsonb_build_object(
        'products', coalesce((
            select jsonb_agg((to_jsonb(row_data) - 'owner_id') order by row_data.created_at)
            from controle_vendas.products row_data
            where row_data.owner_id = (select auth.uid())
        ), '[]'::jsonb),
        'clients', coalesce((
            select jsonb_agg((to_jsonb(row_data) - 'owner_id') order by row_data.created_at)
            from controle_vendas.clients row_data
            where row_data.owner_id = (select auth.uid())
        ), '[]'::jsonb),
        'sales', coalesce((
            select jsonb_agg((to_jsonb(row_data) - 'owner_id') order by row_data.created_at)
            from controle_vendas.sales row_data
            where row_data.owner_id = (select auth.uid())
        ), '[]'::jsonb),
        'sale_items', coalesce((
            select jsonb_agg((to_jsonb(row_data) - 'owner_id') order by row_data.created_at)
            from controle_vendas.sale_items row_data
            where row_data.owner_id = (select auth.uid())
        ), '[]'::jsonb)
    );
end;
$$;

revoke all on function public.controle_vendas_save_product(jsonb) from public, anon;
revoke all on function public.controle_vendas_save_client(jsonb) from public, anon;
revoke all on function public.controle_vendas_save_sale(jsonb, jsonb, bigint) from public, anon;
revoke all on function public.controle_vendas_delete_sale(uuid, bigint) from public, anon;
revoke all on function public.controle_vendas_snapshot() from public, anon;
grant execute on function public.controle_vendas_save_product(jsonb) to authenticated;
grant execute on function public.controle_vendas_save_client(jsonb) to authenticated;
grant execute on function public.controle_vendas_save_sale(jsonb, jsonb, bigint) to authenticated;
grant execute on function public.controle_vendas_delete_sale(uuid, bigint) to authenticated;
grant execute on function public.controle_vendas_snapshot() to authenticated;
