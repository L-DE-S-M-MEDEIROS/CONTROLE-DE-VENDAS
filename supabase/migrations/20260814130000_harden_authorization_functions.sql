create or replace function private.vendas_pro_is_authorized()
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

create or replace function private.vendas_pro_can_edit()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select private.vendas_pro_is_authorized();
$$;

revoke all on function private.vendas_pro_is_authorized() from public, anon;
revoke all on function private.vendas_pro_can_edit() from public, anon;
grant usage on schema private to authenticated;
grant execute on function private.vendas_pro_is_authorized() to authenticated;
grant execute on function private.vendas_pro_can_edit() to authenticated;

create or replace function public.vendas_pro_is_authorized()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
    select private.vendas_pro_is_authorized();
$$;

create or replace function public.vendas_pro_can_edit()
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
    select private.vendas_pro_can_edit();
$$;
