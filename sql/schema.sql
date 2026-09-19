-- PA Intake schema (Supabase / Postgres)
-- Run in Supabase SQL editor or via psql.

create table if not exists payer_aliases (
  alias text primary key,
  canonical_payer text not null
);

create table if not exists drug_aliases (
  alias text primary key,
  canonical_drug text not null,
  drug_class text not null
);

create table if not exists payer_policies (
  id uuid primary key default gen_random_uuid(),
  payer_name text not null,
  drug_name text not null,
  drug_class text not null,
  diagnosis_code text not null,
  requires_pa boolean not null,
  criteria jsonb not null default '[]'::jsonb,
  -- criteria items: {"id":"c1","text":"...","weight":1.0}
  historical_approval_rate numeric default 0.7,
  created_at timestamptz default now(),
  unique (payer_name, drug_name, diagnosis_code)
);

create table if not exists formulary_alternatives (
  id uuid primary key default gen_random_uuid(),
  payer_name text not null,
  drug_class text not null,
  original_drug text not null,
  alternative_drug text not null,
  requires_pa boolean not null default false
);

create table if not exists pa_cases (
  case_id uuid primary key default gen_random_uuid(),
  drug_name text,
  diagnosis_code text,
  payer_name text,
  drug_class text,
  clinical_note text,
  policy_lookup text,
  pa_required boolean,
  policy_criteria jsonb,
  extractions jsonb,
  draft_pa_form jsonb,
  missing_fields jsonb,
  approval_likelihood numeric,
  alternative_suggestion text,
  status text check (status in ('no_pa_required','auto_completed','needs_review')),
  human_review_notes text,
  error_log jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
