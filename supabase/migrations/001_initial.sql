-- 001_initial: everything the portal stores today in data/clients/, as tables.
--
-- Access model: only the portal's server talks to this database, with the
-- secret (service_role) key, which bypasses row-level security. Every table
-- has RLS switched on and NO policies, and the browser-facing roles (anon,
-- authenticated) have no grants at all -- so the publishable key, if it ever
-- leaked, reads nothing. Permissions stay in the application (auth.py), where
-- they are tested.
--
-- The shape mirrors casefile.CaseStore one to one, so the database store is a
-- drop-in replacement for the folder store.

create schema if not exists app;
revoke all on schema app from public, anon, authenticated;

-- ---------------------------------------------------------------- accounts

create table app.users (
  email          text primary key check (email = lower(email)),
  name           text not null,
  role           text not null check (role in ('berater', 'unternehmen', 'steuerberater')),
  password_hash  text not null,                 -- PBKDF2, see auth.hash_password
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

-- Sessions live here because serverless functions keep no memory between
-- requests. Only a SHA-256 of the cookie token is stored.
create table app.sessions (
  token_sha256   text primary key,
  email          text not null references app.users (email) on delete cascade,
  created_at     timestamptz not null default now(),
  expires_at     timestamptz not null
);
create index sessions_expiry on app.sessions (expires_at);

-- Failed logins, for the temporary lockout (SessionManager.locked_out).
create table app.login_failures (
  id             bigint generated always as identity primary key,
  email          text not null,
  at             timestamptz not null default now()
);
create index login_failures_email_at on app.login_failures (email, at);

-- ---------------------------------------------------------------- cases

-- CRA-YYYY-NNNN, numbered per year without gaps from races.
create table app.case_counters (
  year           int primary key,
  last_number    int not null
);

create table app.cases (
  case_id        text primary key check (case_id ~ '^CRA-\d{4}-\d{4}$'),
  -- The case record (stage, history, members, orders, notes, ...) as the
  -- folder store keeps it in case_meta.json; the columns below are copies
  -- for listing and filtering.
  meta           jsonb not null,
  company_name   text not null,
  stage          text not null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);

create table app.answers (
  case_id        text not null references app.cases (case_id) on delete cascade,
  audience       text not null check (audience in ('unternehmen', 'steuerberater')),
  data           jsonb not null,
  updated_at     timestamptz not null default now(),
  primary key (case_id, audience)
);

-- The file itself sits in Storage (bucket case-files, path <case_id>/<doc_id>/<name>).
create table app.documents (
  doc_id         text primary key check (doc_id ~ '^[a-f0-9]{12}$'),
  case_id        text not null references app.cases (case_id) on delete cascade,
  doc_type       text not null,
  filename       text not null,
  storage_path   text not null unique,
  size           bigint not null check (size > 0 and size <= 26214400),
  sha256         text not null,
  uploaded_at    timestamptz not null default now(),
  meta           jsonb not null default '{}'::jsonb
);
create index documents_case on app.documents (case_id);

-- Generated outputs: report, summary, letters (text, small).
create table app.artifacts (
  case_id        text not null references app.cases (case_id) on delete cascade,
  name           text not null check (name ~ '^[a-z0-9][a-z0-9_\-]{0,80}\.(md|html|json|csv)$'),
  content        text not null,
  updated_at     timestamptz not null default now(),
  primary key (case_id, name)
);

-- Signed agreements and messages. Append-only: the trigger below refuses
-- UPDATE and DELETE, so a signature can never be edited after the fact
-- (GDPR Art. 7(1) -- the proof must hold). Deleting the whole case still
-- removes them, through the cascade.
create table app.records (
  id             bigint generated always as identity primary key,
  case_id        text not null references app.cases (case_id) on delete cascade,
  kind           text not null check (kind in ('agreements', 'messages')),
  record         jsonb not null,
  created_at     timestamptz not null default now()
);
create index records_case_kind on app.records (case_id, kind, id);

create function app.refuse_change() returns trigger language plpgsql as $$
begin
  -- Rows vanish only with their case (ON DELETE CASCADE runs as a DELETE
  -- whose parent row is already gone).
  if tg_op = 'DELETE' and not exists (select 1 from app.cases c where c.case_id = old.case_id) then
    return old;
  end if;
  raise exception 'app.records is append-only';
end $$;

create trigger records_append_only before update or delete on app.records
  for each row execute function app.refuse_change();

-- One row per engagement: the outcome log (casefile.append_outcome).
create table app.outcomes (
  id             bigint generated always as identity primary key,
  row            jsonb not null,
  created_at     timestamptz not null default now()
);

-- ---------------------------------------------------------------- lock down

do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'app' loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on app.%I from public, anon, authenticated', t);
  end loop;
end $$;

grant usage on schema app to service_role;
grant all on all tables in schema app to service_role;
grant all on all sequences in schema app to service_role;

-- ---------------------------------------------------------------- storage

-- Private bucket: no public URLs; the server streams files after its own
-- permission check. 25 MB per file, as MAX_UPLOAD_BYTES.
insert into storage.buckets (id, name, public, file_size_limit)
values ('case-files', 'case-files', false, 26214400)
on conflict (id) do nothing;
