delete from private.vendas_pro_authorized_users
where email <> 'vendasldesmmedeiros@gmail.com';

alter table private.vendas_pro_authorized_users
drop column if exists access_role;

create or replace function public.vendas_pro_can_edit()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select public.vendas_pro_is_authorized();
$$;

drop function if exists public.vendas_pro_current_role();

revoke all on function public.vendas_pro_can_edit() from public, anon;
grant execute on function public.vendas_pro_can_edit() to authenticated;
