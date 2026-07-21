-- Supabase schema for マルハン綾瀬上土棚店・設定狙い分析
-- Run this file in Supabase SQL Editor after creating the project.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
  display_name text,
  role text not null default 'viewer' check (role in ('admin', 'viewer')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.machine_records (
  id uuid primary key default gen_random_uuid(),
  store_name text not null,
  date date not null,
  machine_no integer not null,
  machine_name text not null,
  games integer not null default 0,
  diff_coins integer not null default 0,
  bb integer not null default 0,
  rb integer not null default 0,
  at_hits integer not null default 0,
  first_hits integer not null default 0,
  special_day boolean not null default false,
  source_url text not null,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint machine_records_store_date_machine_unique unique (store_name, date, machine_no)
);

create table if not exists public.import_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  source_url text not null,
  target_date date,
  status text not null check (status in ('success', 'error')),
  records_found integer not null default 0,
  records_added integer not null default 0,
  error_message text,
  created_at timestamptz not null default now()
);

create table if not exists public.store_calendar (
  id uuid primary key default gen_random_uuid(),
  store_name text not null,
  date date not null,
  special_day boolean not null default false,
  event_name text,
  memo text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint store_calendar_store_date_unique unique (store_name, date)
);

create index if not exists idx_machine_records_store_date on public.machine_records (store_name, date);
create index if not exists idx_machine_records_machine_no on public.machine_records (machine_no);
create index if not exists idx_machine_records_machine_name on public.machine_records (machine_name);
create index if not exists idx_import_logs_created_at on public.import_logs (created_at desc);
create index if not exists idx_store_calendar_store_date on public.store_calendar (store_name, date);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists set_profiles_updated_at on public.profiles;
create trigger set_profiles_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists set_machine_records_updated_at on public.machine_records;
create trigger set_machine_records_updated_at
before update on public.machine_records
for each row execute function public.set_updated_at();

drop trigger if exists set_store_calendar_updated_at on public.store_calendar;
create trigger set_store_calendar_updated_at
before update on public.store_calendar
for each row execute function public.set_updated_at();

create or replace function public.is_admin(check_user_id uuid default auth.uid())
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.profiles
    where id = check_user_id
      and role = 'admin'
  );
$$;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, display_name, role)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1)),
    'viewer'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

create or replace function public.prevent_unauthorized_role_change()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if old.role is distinct from new.role then
    if coalesce(auth.role(), '') = 'service_role' then
      return new;
    end if;
    if not public.is_admin(auth.uid()) then
      raise exception 'Only admins can change user roles';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists prevent_unauthorized_role_change on public.profiles;
create trigger prevent_unauthorized_role_change
before update on public.profiles
for each row execute function public.prevent_unauthorized_role_change();

create or replace function public.list_profiles_for_admin()
returns table (
  id uuid,
  email text,
  display_name text,
  role text,
  created_at timestamptz,
  updated_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_admin(auth.uid()) then
    raise exception 'permission denied';
  end if;

  return query
    select p.id, p.email, p.display_name, p.role, p.created_at, p.updated_at
    from public.profiles p
    order by p.created_at desc;
end;
$$;

create or replace function public.set_user_role(target_user_id uuid, new_role text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_admin(auth.uid()) then
    raise exception 'permission denied';
  end if;
  if new_role not in ('admin', 'viewer') then
    raise exception 'invalid role';
  end if;

  update public.profiles
  set role = new_role,
      updated_at = now()
  where id = target_user_id;
end;
$$;

alter table public.profiles enable row level security;
alter table public.machine_records enable row level security;
alter table public.import_logs enable row level security;
alter table public.store_calendar enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own
on public.profiles for select
to authenticated
using (id = auth.uid());

drop policy if exists profiles_insert_own_viewer on public.profiles;
create policy profiles_insert_own_viewer
on public.profiles for insert
to authenticated
with check (id = auth.uid() and role = 'viewer');

drop policy if exists profiles_update_own_display on public.profiles;
create policy profiles_update_own_display
on public.profiles for update
to authenticated
using (id = auth.uid())
with check (id = auth.uid());

drop policy if exists profiles_admin_update on public.profiles;
create policy profiles_admin_update
on public.profiles for update
to authenticated
using (public.is_admin(auth.uid()))
with check (public.is_admin(auth.uid()));

drop policy if exists machine_records_select_authenticated on public.machine_records;
create policy machine_records_select_authenticated
on public.machine_records for select
to authenticated
using (true);

drop policy if exists machine_records_insert_admin on public.machine_records;
create policy machine_records_insert_admin
on public.machine_records for insert
to authenticated
with check (public.is_admin(auth.uid()));

drop policy if exists machine_records_update_admin on public.machine_records;
create policy machine_records_update_admin
on public.machine_records for update
to authenticated
using (public.is_admin(auth.uid()))
with check (public.is_admin(auth.uid()));

drop policy if exists machine_records_delete_admin on public.machine_records;
create policy machine_records_delete_admin
on public.machine_records for delete
to authenticated
using (public.is_admin(auth.uid()));

drop policy if exists store_calendar_select_authenticated on public.store_calendar;
create policy store_calendar_select_authenticated
on public.store_calendar for select
to authenticated
using (true);

drop policy if exists store_calendar_insert_admin on public.store_calendar;
create policy store_calendar_insert_admin
on public.store_calendar for insert
to authenticated
with check (public.is_admin(auth.uid()));

drop policy if exists store_calendar_update_admin on public.store_calendar;
create policy store_calendar_update_admin
on public.store_calendar for update
to authenticated
using (public.is_admin(auth.uid()))
with check (public.is_admin(auth.uid()));

drop policy if exists store_calendar_delete_admin on public.store_calendar;
create policy store_calendar_delete_admin
on public.store_calendar for delete
to authenticated
using (public.is_admin(auth.uid()));

drop policy if exists import_logs_insert_admin on public.import_logs;
create policy import_logs_insert_admin
on public.import_logs for insert
to authenticated
with check (public.is_admin(auth.uid()) and (user_id = auth.uid() or user_id is null));

drop policy if exists import_logs_select_admin on public.import_logs;
create policy import_logs_select_admin
on public.import_logs for select
to authenticated
using (public.is_admin(auth.uid()));

grant usage on schema public to anon, authenticated;
grant select, insert, update on public.profiles to authenticated;
grant select, insert, update, delete on public.machine_records to authenticated;
grant select, insert, update, delete on public.store_calendar to authenticated;
grant select, insert on public.import_logs to authenticated;
grant execute on function public.list_profiles_for_admin() to authenticated;
grant execute on function public.set_user_role(uuid, text) to authenticated;

