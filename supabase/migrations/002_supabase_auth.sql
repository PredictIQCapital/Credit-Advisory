-- 002_supabase_auth: accounts move to Supabase Auth; app.users keeps the profile.
--
-- Passwords are now held and checked by Supabase Auth (bcrypt, rate limits,
-- password reset). app.users keeps what the portal needs to decide access --
-- name and role -- linked to the Auth user by its id. The role lives here,
-- not in user_metadata, because users can edit their own user_metadata.

alter table app.users alter column password_hash drop not null;
alter table app.users add column auth_id uuid unique references auth.users (id) on delete cascade;

comment on column app.users.password_hash is
  'Unused since 002: passwords are held by Supabase Auth. Kept only for the local file store.';

-- Case numbers CRA-YYYY-NNNN, gap-free and safe under concurrent requests:
-- the upsert takes a row lock on the year's counter.
create function app.next_case_id(p_year int) returns text
language sql volatile security definer set search_path = app as $$
  insert into app.case_counters as c (year, last_number) values (p_year, 1)
  on conflict (year) do update set last_number = c.last_number + 1
  returning format('CRA-%s-%s', p_year, lpad(last_number::text, 4, '0'));
$$;
revoke all on function app.next_case_id(int) from public, anon, authenticated;
grant execute on function app.next_case_id(int) to service_role;
