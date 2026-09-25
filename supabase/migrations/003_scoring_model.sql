-- 003_scoring_model: the scoring model as versioned data, stored results,
-- an audit trail, and SQL functions that score from the published model.
--
-- The rules themselves are written and tested in Python. What lives here is
-- (1) a read-only copy of each model version that was ever used, published by
-- scripts/publish_scoring_model.py; (2) every score the portal produced,
-- stamped with its model version; (3) who changed what on a case. Together
-- they answer, years later: "which rules produced this score, from which data?"

-- ======================================================================
-- scoring: one immutable copy per model version
-- ======================================================================

create schema if not exists scoring;
revoke all on schema scoring from public, anon, authenticated;

create table scoring.model_versions (
  version        text primary key check (version ~ '^m-[0-9a-f]{12}$'),
  content_sha256 text not null,
  published_at   timestamptz not null default now(),
  description    text not null default ''
);

create table scoring.factors (
  version            text not null references scoring.model_versions on delete restrict,
  key                text not null,
  position           int not null,
  label              text not null,
  weight             numeric not null check (weight > 0 and weight < 1),
  unit               text not null,
  source             text not null,
  note               text not null default '',
  calibrated         boolean not null,
  higher_is_better   boolean,
  bundesbank_metric  text,
  primary key (version, key)
);

-- Piecewise-linear score curves. sector/size_class '*' is the generic curve;
-- other rows are the sector- and size-specific curves of the calibrated
-- factors (ADR-005). A factor/sector/size without rows uses the generic one.
create table scoring.curves (
  version     text not null,
  factor_key  text not null,
  sector      text not null,
  size_class  text not null,
  seq         int not null,
  x           numeric not null,
  score       numeric not null check (score between 0 and 100),
  basis       text not null,
  primary key (version, factor_key, sector, size_class, seq),
  foreign key (version, factor_key) references scoring.factors (version, key)
);

create table scoring.bands (
  version         text not null references scoring.model_versions,
  band            text not null check (band in ('A', 'B', 'C', 'D', 'E')),
  min_score       numeric not null,
  interpretation  text not null,
  primary key (version, band)
);

create table scoring.settings (
  version  text not null references scoring.model_versions,
  key      text not null,
  value    jsonb not null,
  primary key (version, key)
);

create table scoring.sectors (
  version         text not null references scoring.model_versions,
  sector          text not null,
  label_en        text not null,
  has_benchmarks  boolean not null,
  primary key (version, sector)
);

create table scoring.nace_ranges (
  version        text not null references scoring.model_versions,
  from_division  int not null,
  to_division    int not null,
  sector         text not null,
  primary key (version, from_division)
);

create table scoring.nace_sections (
  version        text not null references scoring.model_versions,
  from_division  int not null,
  to_division    int not null,
  section        text not null,
  primary key (version, from_division)
);

create table scoring.knockouts (
  version    text not null references scoring.model_versions,
  code       text not null,
  title      text not null,
  condition  text not null,
  source     text not null,
  primary key (version, code)
);

-- Bundesbank firm-level quartiles (Jahresabschlussstatistik), five years.
create table scoring.benchmarks (
  version     text not null references scoring.model_versions,
  sector      text not null,
  size_class  text not null,
  metric      text not null,
  year        int not null,
  q25         numeric,
  q50         numeric,
  q75         numeric,
  edition     text,
  primary key (version, sector, size_class, metric, year)
);

-- A published model is never edited: a change is a new version.
create function scoring.refuse_change() returns trigger language plpgsql as $$
begin
  raise exception 'scoring.% is read-only once published -- publish a new model version', tg_table_name;
end $$;

do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'scoring' loop
    execute format('create trigger %I before update or delete on scoring.%I
                    for each row execute function scoring.refuse_change()', t || '_read_only', t);
    execute format('alter table scoring.%I enable row level security', t);
    execute format('revoke all on scoring.%I from public, anon, authenticated', t);
  end loop;
end $$;

grant usage on schema scoring to service_role;
grant select, insert on all tables in schema scoring to service_role;

-- ----------------------------------------------------------------- functions

create function scoring.current_version() returns text language sql stable as $$
  select version from scoring.model_versions order by published_at desc, version limit 1;
$$;

-- The Bundesbank size class for a revenue figure (same classes as benchmarks.py).
create function scoring.size_class(p_revenue numeric) returns text language sql immutable as $$
  select case
    when p_revenue is null or p_revenue <= 0 then '2_bis_10m'
    when p_revenue < 2000000 then 'unter_2m'
    when p_revenue < 10000000 then '2_bis_10m'
    when p_revenue < 50000000 then '10_bis_50m'
    else 'ab_50m' end;
$$;

-- Piecewise-linear lookup, clamped at both ends -- scorecard.interpolate in SQL.
-- Uses the sector/size curve when the model has one, else the generic curve.
create function scoring.interpolate(
  p_x numeric, p_factor text, p_sector text default '*', p_size_class text default '*',
  p_version text default null
) returns numeric language plpgsql stable as $$
declare
  v text := coalesce(p_version, scoring.current_version());
  sec text := p_sector;
  siz text := p_size_class;
  pts record;
  prev_x numeric; prev_y numeric;
  first boolean := true;
begin
  if not exists (select 1 from scoring.curves c where c.version = v and c.factor_key = p_factor
                   and c.sector = sec and c.size_class = siz) then
    sec := '*'; siz := '*';
  end if;
  for pts in select c.x, c.score from scoring.curves c
             where c.version = v and c.factor_key = p_factor and c.sector = sec and c.size_class = siz
             order by c.seq loop
    if first then
      if p_x <= pts.x then return pts.score; end if;
      first := false;
    elsif p_x <= pts.x then
      if pts.x = prev_x then return pts.score; end if;
      return prev_y + (p_x - prev_x) / (pts.x - prev_x) * (pts.score - prev_y);
    end if;
    prev_x := pts.x; prev_y := pts.score;
  end loop;
  return prev_y;          -- beyond the last point (null for an unknown factor)
end $$;

-- A factor's points for a company: its sector and revenue pick the curve.
create function scoring.factor_score(
  p_factor text, p_value numeric, p_sector text, p_revenue numeric, p_version text default null
) returns numeric language sql stable as $$
  select scoring.interpolate(p_value, p_factor, p_sector, scoring.size_class(p_revenue), p_version);
$$;

create function scoring.band_for(p_score numeric, p_version text default null) returns text
language sql stable as $$
  select band from scoring.bands
  where version = coalesce(p_version, scoring.current_version()) and p_score >= min_score
  order by min_score desc limit 1;
$$;

-- WZ 2008 / NACE code -> benchmark sector (nace.py). Null for a malformed code,
-- and for a section letter that does not match the division ("F25" is a typo).
create function scoring.sector_for_nace(p_code text, p_version text default null) returns text
language plpgsql stable as $$
declare
  v text := coalesce(p_version, scoring.current_version());
  m text[] := regexp_match(coalesce(p_code, ''),
                '^\s*([A-Ua-u])?\s*(\d{2})(?:\.(\d{1,2})(?:\.(\d))?|(\d{2}))?\s*$');
  division int;
  section text;
begin
  if m is null then return null; end if;
  division := m[2]::int;
  select s.section into section from scoring.nace_sections s
   where s.version = v and division between s.from_division and s.to_division;
  if section is null or (m[1] is not null and upper(m[1]) <> section) then
    return null;
  end if;
  return coalesce((select r.sector from scoring.nace_ranges r
                    where r.version = v and division between r.from_division and r.to_division),
                  'Andere Branche');
end $$;

revoke all on all functions in schema scoring from public, anon, authenticated;
grant execute on all functions in schema scoring to service_role;

-- ======================================================================
-- app: stored results, audit trail, timestamps, views
-- ======================================================================

-- Every quick check and every report, stamped with its model version.
-- model_version is not a foreign key on purpose: a result must never be lost
-- because its model version has not been published yet; the view
-- app.v_unpublished_models lists any such gap.
create table app.results (
  id              bigint generated always as identity primary key,
  case_id         text not null references app.cases (case_id) on delete cascade,
  kind            text not null check (kind in ('quick', 'report')),
  model_version   text not null,
  band            text not null check (band in ('A', 'B', 'C', 'D', 'E')),
  score           numeric not null,
  score_generic   numeric,
  band_generic    text,
  verdict         text not null,
  sector          text not null,
  nace_code       text,
  size_class      text,
  coverage        numeric,
  created_by      text,
  created_at      timestamptz not null default now(),
  summary         jsonb not null
);
create index results_case on app.results (case_id, created_at desc);
create index results_model on app.results (model_version);

create table app.result_factors (
  result_id    bigint not null references app.results (id) on delete cascade,
  factor_key   text not null,
  value        numeric,
  score        numeric,
  weight       numeric not null,
  points_lost  numeric not null,
  basis        text not null,
  primary key (result_id, factor_key)
);

-- Results are evidence: append-only, gone only with their case.
create trigger results_append_only before update or delete on app.results
  for each row execute function app.refuse_change();

create function app.refuse_child_change() returns trigger language plpgsql as $$
begin
  if tg_op = 'DELETE' and not exists (select 1 from app.results r where r.id = old.result_id) then
    return old;
  end if;
  raise exception 'app.result_factors is append-only';
end $$;

create trigger result_factors_append_only before update or delete on app.result_factors
  for each row execute function app.refuse_child_change();

-- ----------------------------------------------------------------- audit trail
-- Who changed what on a case: answers, documents and the case record.
-- Rows go with their case (ON DELETE CASCADE), so deleting an account under
-- GDPR Art. 17 also deletes its trail.

create table app.audit_log (
  id          bigint generated always as identity primary key,
  case_id     text not null references app.cases (case_id) on delete cascade,
  at          timestamptz not null default now(),
  table_name  text not null,
  op          text not null,
  row_key     text,
  changed     jsonb
);
create index audit_case on app.audit_log (case_id, at desc);

create trigger audit_append_only before update on app.audit_log
  for each row execute function app.refuse_change();

create function app.audit() returns trigger language plpgsql as $$
declare
  cid text := coalesce(new.case_id, old.case_id);
  diff jsonb;
begin
  -- A cascade from a deleted case writes nothing: the case and its trail go together.
  if not exists (select 1 from app.cases c where c.case_id = cid) then
    return null;
  end if;
  if tg_table_name = 'cases' then
    -- Only the top-level fields of the case record that changed.
    select jsonb_object_agg(k, jsonb_build_object('old', old.meta -> k, 'new', new.meta -> k))
      into diff
      from (select jsonb_object_keys(old.meta || new.meta) as k) keys
     where k <> 'updated_at' and (old.meta -> k) is distinct from (new.meta -> k);
    if diff is null then return null; end if;
    insert into app.audit_log (case_id, table_name, op, row_key, changed)
    values (cid, tg_table_name, tg_op, cid, diff);
  elsif tg_table_name = 'answers' then
    insert into app.audit_log (case_id, table_name, op, row_key, changed)
    values (cid, tg_table_name, tg_op, coalesce(new.audience, old.audience),
            case when tg_op = 'DELETE' then null else to_jsonb(new.data) end);
  else  -- documents: which file, never the content
    insert into app.audit_log (case_id, table_name, op, row_key, changed)
    values (cid, tg_table_name, tg_op, coalesce(new.doc_id, old.doc_id),
            jsonb_build_object('doc_type', coalesce(new.doc_type, old.doc_type),
                               'filename', coalesce(new.filename, old.filename),
                               'meta', coalesce(new.meta, old.meta)));
  end if;
  return null;
end $$;

create trigger cases_audit after update on app.cases
  for each row execute function app.audit();
create trigger answers_audit after insert or update or delete on app.answers
  for each row execute function app.audit();
create trigger documents_audit after insert or update or delete on app.documents
  for each row execute function app.audit();

-- ----------------------------------------------------------------- timestamps

create function app.touch_updated_at() returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

create trigger cases_touch before update on app.cases for each row execute function app.touch_updated_at();
create trigger answers_touch before update on app.answers for each row execute function app.touch_updated_at();
create trigger artifacts_touch before update on app.artifacts for each row execute function app.touch_updated_at();
create trigger users_touch before update on app.users for each row execute function app.touch_updated_at();

-- ----------------------------------------------------------------- views

create view app.v_latest_results with (security_invoker = true) as
  select distinct on (case_id) r.*
  from app.results r
  order by case_id, created_at desc, id desc;

create view app.v_pipeline with (security_invoker = true) as
  select c.stage, count(*) as cases,
         count(*) filter (where lr.band in ('A', 'B')) as band_a_b,
         count(*) filter (where lr.band = 'C') as band_c,
         count(*) filter (where lr.band in ('D', 'E')) as band_d_e,
         count(*) filter (where lr.case_id is null) as without_result
  from app.cases c
  left join app.v_latest_results lr on lr.case_id = c.case_id
  group by c.stage;

create view app.v_band_distribution with (security_invoker = true) as
  select sector, band, count(*) as cases, round(avg(score), 1) as avg_score
  from app.v_latest_results
  group by sector, band;

create view app.v_unpublished_models with (security_invoker = true) as
  select r.model_version, count(*) as results, min(r.created_at) as first_used
  from app.results r
  where not exists (select 1 from scoring.model_versions m where m.version = r.model_version)
  group by r.model_version;

-- ----------------------------------------------------------------- lock down

do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'app' loop
    execute format('alter table app.%I enable row level security', t);
    execute format('revoke all on app.%I from public, anon, authenticated', t);
  end loop;
end $$;

revoke all on app.v_latest_results, app.v_pipeline, app.v_band_distribution, app.v_unpublished_models
  from public, anon, authenticated;
grant all on all tables in schema app to service_role;
grant all on all sequences in schema app to service_role;
revoke all on function app.audit(), app.touch_updated_at(), app.refuse_child_change()
  from public, anon, authenticated;
