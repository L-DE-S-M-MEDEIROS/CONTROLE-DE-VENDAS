alter table private.vendas_pro_authorized_users
add column if not exists access_role text not null default 'viewer'
check (access_role in ('operator', 'viewer'));

update private.vendas_pro_authorized_users
set access_role = 'operator'
where email = 'vendasldesmmedeiros@gmail.com';

create or replace function public.vendas_pro_can_edit()
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
          and allowed.access_role = 'operator'
    );
$$;

create or replace function public.vendas_pro_current_role()
returns text
language sql
stable
security definer
set search_path = ''
as $$
    select allowed.access_role
    from private.vendas_pro_authorized_users allowed
    where allowed.user_id = (select auth.uid())
      and allowed.email = lower(coalesce((select auth.jwt() ->> 'email'), ''));
$$;

revoke all on function public.vendas_pro_can_edit() from public, anon;
revoke all on function public.vendas_pro_current_role() from public, anon;
grant execute on function public.vendas_pro_can_edit() to authenticated;
grant execute on function public.vendas_pro_current_role() to authenticated;

alter table public.vendas_pro_products
add column if not exists revision bigint not null default 1 check (revision > 0);
alter table public.vendas_pro_clients
add column if not exists revision bigint not null default 1 check (revision > 0);
alter table public.vendas_pro_sales
add column if not exists revision bigint not null default 1 check (revision > 0);
alter table public.vendas_pro_sale_items
add column if not exists revision bigint not null default 1 check (revision > 0);

drop policy vendas_pro_products_select on public.vendas_pro_products;
drop policy vendas_pro_products_insert on public.vendas_pro_products;
drop policy vendas_pro_products_update on public.vendas_pro_products;
drop policy vendas_pro_products_delete on public.vendas_pro_products;
create policy vendas_pro_products_select on public.vendas_pro_products
for select to authenticated using ((select public.vendas_pro_is_authorized()));
create policy vendas_pro_products_insert on public.vendas_pro_products
for insert to authenticated
with check ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));
create policy vendas_pro_products_update on public.vendas_pro_products
for update to authenticated
using ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()))
with check ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));
create policy vendas_pro_products_delete on public.vendas_pro_products
for delete to authenticated
using ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));

drop policy vendas_pro_clients_select on public.vendas_pro_clients;
drop policy vendas_pro_clients_insert on public.vendas_pro_clients;
drop policy vendas_pro_clients_update on public.vendas_pro_clients;
drop policy vendas_pro_clients_delete on public.vendas_pro_clients;
create policy vendas_pro_clients_select on public.vendas_pro_clients
for select to authenticated using ((select public.vendas_pro_is_authorized()));
create policy vendas_pro_clients_insert on public.vendas_pro_clients
for insert to authenticated
with check ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));
create policy vendas_pro_clients_update on public.vendas_pro_clients
for update to authenticated
using ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()))
with check ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));
create policy vendas_pro_clients_delete on public.vendas_pro_clients
for delete to authenticated
using ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));

drop policy vendas_pro_sales_select on public.vendas_pro_sales;
drop policy vendas_pro_sales_insert on public.vendas_pro_sales;
drop policy vendas_pro_sales_update on public.vendas_pro_sales;
drop policy vendas_pro_sales_delete on public.vendas_pro_sales;
create policy vendas_pro_sales_select on public.vendas_pro_sales
for select to authenticated using ((select public.vendas_pro_is_authorized()));
create policy vendas_pro_sales_insert on public.vendas_pro_sales
for insert to authenticated
with check ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));
create policy vendas_pro_sales_update on public.vendas_pro_sales
for update to authenticated
using ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()))
with check ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));
create policy vendas_pro_sales_delete on public.vendas_pro_sales
for delete to authenticated
using ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));

drop policy vendas_pro_sale_items_select on public.vendas_pro_sale_items;
drop policy vendas_pro_sale_items_insert on public.vendas_pro_sale_items;
drop policy vendas_pro_sale_items_update on public.vendas_pro_sale_items;
drop policy vendas_pro_sale_items_delete on public.vendas_pro_sale_items;
create policy vendas_pro_sale_items_select on public.vendas_pro_sale_items
for select to authenticated using ((select public.vendas_pro_is_authorized()));
create policy vendas_pro_sale_items_insert on public.vendas_pro_sale_items
for insert to authenticated
with check ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));
create policy vendas_pro_sale_items_update on public.vendas_pro_sale_items
for update to authenticated
using ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()))
with check ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));
create policy vendas_pro_sale_items_delete on public.vendas_pro_sale_items
for delete to authenticated
using ((select public.vendas_pro_can_edit()) and owner_id = (select auth.uid()));

create or replace function public.vendas_pro_save_product(product_record jsonb)
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
    if not (select public.vendas_pro_can_edit()) then
        raise exception 'Acesso somente para visualização' using errcode = '42501';
    end if;
    if exists (select 1 from public.vendas_pro_products where id=target_id) then
        update public.vendas_pro_products set
            name=product_record ->> 'name',
            price_cents=(product_record ->> 'price_cents')::bigint,
            barcode=product_record ->> 'barcode',
            active=(product_record ->> 'active')::boolean,
            deleted_at=(product_record ->> 'deleted_at')::timestamptz,
            revision=revision+1
        where id=target_id and owner_id=(select auth.uid()) and revision=expected
        returning revision into new_revision;
        if new_revision is null then
            raise exception 'VENDAS_PRO_CONFLICT:product' using errcode = '40001';
        end if;
    else
        if expected <> 0 then
            raise exception 'VENDAS_PRO_CONFLICT:product' using errcode = '40001';
        end if;
        insert into public.vendas_pro_products(
            id, owner_id, name, price_cents, barcode, active, created_at, deleted_at, revision
        ) values (
            target_id, (select auth.uid()), product_record ->> 'name',
            (product_record ->> 'price_cents')::bigint, product_record ->> 'barcode',
            (product_record ->> 'active')::boolean,
            coalesce((product_record ->> 'created_at')::timestamptz, now()),
            (product_record ->> 'deleted_at')::timestamptz, 1
        ) returning revision into new_revision;
    end if;
    return new_revision;
end;
$$;

create or replace function public.vendas_pro_save_client(client_record jsonb)
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
    if not (select public.vendas_pro_can_edit()) then
        raise exception 'Acesso somente para visualização' using errcode = '42501';
    end if;
    if exists (select 1 from public.vendas_pro_clients where id=target_id) then
        update public.vendas_pro_clients set
            name=client_record ->> 'name',
            notes=coalesce(client_record ->> 'notes', ''),
            active=(client_record ->> 'active')::boolean,
            deleted_at=(client_record ->> 'deleted_at')::timestamptz,
            revision=revision+1
        where id=target_id and owner_id=(select auth.uid()) and revision=expected
        returning revision into new_revision;
        if new_revision is null then
            raise exception 'VENDAS_PRO_CONFLICT:client' using errcode = '40001';
        end if;
    else
        if expected <> 0 then
            raise exception 'VENDAS_PRO_CONFLICT:client' using errcode = '40001';
        end if;
        insert into public.vendas_pro_clients(
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

drop function public.vendas_pro_save_sale(jsonb, jsonb);
create function public.vendas_pro_save_sale(
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
    if not (select public.vendas_pro_can_edit()) then
        raise exception 'Acesso somente para visualização' using errcode = '42501';
    end if;
    if not exists (
        select 1 from public.vendas_pro_clients
        where id=target_client_id and deleted_at is null
    ) then
        raise exception 'Cliente remoto inválido' using errcode = '23503';
    end if;
    if exists (select 1 from public.vendas_pro_sales where id=target_sale_id) then
        update public.vendas_pro_sales set
            client_id=target_client_id,
            sale_date=(sale_record ->> 'sale_date')::date,
            total_cents=(sale_record ->> 'total_cents')::bigint,
            deleted_at=null,
            revision=revision+1
        where id=target_sale_id
          and owner_id=(select auth.uid())
          and revision=expected_revision
        returning revision into new_revision;
        if new_revision is null then
            raise exception 'VENDAS_PRO_CONFLICT:sale' using errcode = '40001';
        end if;
    else
        if expected_revision <> 0 then
            raise exception 'VENDAS_PRO_CONFLICT:sale' using errcode = '40001';
        end if;
        insert into public.vendas_pro_sales(
            id, owner_id, client_id, sale_date, total_cents, created_at, revision
        ) values (
            target_sale_id, (select auth.uid()), target_client_id,
            (sale_record ->> 'sale_date')::date,
            (sale_record ->> 'total_cents')::bigint,
            coalesce((sale_record ->> 'created_at')::timestamptz, now()), 1
        ) returning revision into new_revision;
    end if;
    delete from public.vendas_pro_sale_items
    where sale_id=target_sale_id and owner_id=(select auth.uid());
    for item in select value from jsonb_array_elements(item_records)
    loop
        target_product_id := (item ->> 'product_id')::uuid;
        if not exists (
            select 1 from public.vendas_pro_products
            where id=target_product_id and deleted_at is null
        ) then
            raise exception 'Produto remoto inválido' using errcode = '23503';
        end if;
        insert into public.vendas_pro_sale_items(
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

drop function public.vendas_pro_delete_sale(uuid);
create function public.vendas_pro_delete_sale(target_sale_id uuid, expected_revision bigint)
returns bigint
language plpgsql
security invoker
set search_path = ''
as $$
declare
    new_revision bigint;
begin
    if not (select public.vendas_pro_can_edit()) then
        raise exception 'Acesso somente para visualização' using errcode = '42501';
    end if;
    update public.vendas_pro_sales
    set deleted_at=now(), revision=revision+1
    where id=target_sale_id
      and owner_id=(select auth.uid())
      and revision=expected_revision
    returning revision into new_revision;
    if new_revision is null then
        raise exception 'VENDAS_PRO_CONFLICT:sale' using errcode = '40001';
    end if;
    delete from public.vendas_pro_sale_items
    where sale_id=target_sale_id and owner_id=(select auth.uid());
    return new_revision;
end;
$$;

revoke all on function public.vendas_pro_save_product(jsonb) from public, anon;
revoke all on function public.vendas_pro_save_client(jsonb) from public, anon;
revoke all on function public.vendas_pro_save_sale(jsonb, jsonb, bigint) from public, anon;
revoke all on function public.vendas_pro_delete_sale(uuid, bigint) from public, anon;
grant execute on function public.vendas_pro_save_product(jsonb) to authenticated;
grant execute on function public.vendas_pro_save_client(jsonb) to authenticated;
grant execute on function public.vendas_pro_save_sale(jsonb, jsonb, bigint) to authenticated;
grant execute on function public.vendas_pro_delete_sale(uuid, bigint) to authenticated;
