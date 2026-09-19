-- Seed data for PA Intake hackathon demo
-- Idempotent-ish: truncate aliases/policies/alts then insert.

truncate payer_aliases, drug_aliases, payer_policies, formulary_alternatives cascade;

-- Payer aliases
insert into payer_aliases (alias, canonical_payer) values
  ('unitedhealthcare', 'UnitedHealthcare'),
  ('uhc', 'UnitedHealthcare'),
  ('united healthcare', 'UnitedHealthcare'),
  ('aetna', 'Aetna'),
  ('cigna', 'Cigna');

-- Drug aliases
insert into drug_aliases (alias, canonical_drug, drug_class) values
  ('adalimumab', 'adalimumab', 'TNF inhibitor'),
  ('humira', 'adalimumab', 'TNF inhibitor'),
  ('ozempic', 'semaglutide', 'GLP-1 agonist'),
  ('semaglutide', 'semaglutide', 'GLP-1 agonist'),
  ('dupixent', 'dupilumab', 'IL-4/IL-13 inhibitor'),
  ('dupilumab', 'dupilumab', 'IL-4/IL-13 inhibitor'),
  ('enbrel', 'etanercept', 'TNF inhibitor'),
  ('etanercept', 'etanercept', 'TNF inhibitor'),
  ('trulicity', 'dulaglutide', 'GLP-1 agonist'),
  ('dulaglutide', 'dulaglutide', 'GLP-1 agonist');

-- Policies (8 rows across 3 payers × several drugs)
-- Fixture A: Aetna + semaglutide + E11.9 → no PA
insert into payer_policies
  (payer_name, drug_name, drug_class, diagnosis_code, requires_pa, criteria, historical_approval_rate)
values
  (
    'Aetna', 'semaglutide', 'GLP-1 agonist', 'E11.9', false,
    '[]'::jsonb, 0.85
  ),
  -- Fixture B/C: UHC + adalimumab + M06.9 → PA required, 4 criteria
  (
    'UnitedHealthcare', 'adalimumab', 'TNF inhibitor', 'M06.9', true,
    '[
      {"id":"c1","text":"Documented diagnosis of rheumatoid arthritis","weight":1.0},
      {"id":"c2","text":"Inadequate response to methotrexate for at least 3 months","weight":1.2},
      {"id":"c3","text":"Negative TB screening within past 12 months","weight":1.0},
      {"id":"c4","text":"Prescribed by or in consultation with a rheumatologist","weight":0.8}
    ]'::jsonb,
    0.72
  ),
  (
    'UnitedHealthcare', 'adalimumab', 'TNF inhibitor', 'L40.0', true,
    '[
      {"id":"c1","text":"Documented diagnosis of plaque psoriasis","weight":1.0},
      {"id":"c2","text":"Failed topical therapy","weight":1.0},
      {"id":"c3","text":"BSA involvement greater than 10 percent","weight":1.0},
      {"id":"c4","text":"Prescribed by a dermatologist","weight":0.8}
    ]'::jsonb,
    0.68
  ),
  (
    'Cigna', 'dupilumab', 'IL-4/IL-13 inhibitor', 'L20.9', true,
    '[
      {"id":"c1","text":"Documented moderate-to-severe atopic dermatitis","weight":1.0},
      {"id":"c2","text":"Failed two topical corticosteroids","weight":1.0},
      {"id":"c3","text":"IGA score of 3 or higher","weight":1.0},
      {"id":"c4","text":"Prescribed by dermatology or allergy","weight":0.9}
    ]'::jsonb,
    0.70
  ),
  (
    'Cigna', 'dupilumab', 'IL-4/IL-13 inhibitor', 'J45.40', false,
    '[]'::jsonb, 0.90
  ),
  (
    'Aetna', 'adalimumab', 'TNF inhibitor', 'M06.9', true,
    '[
      {"id":"c1","text":"RA diagnosis confirmed","weight":1.0},
      {"id":"c2","text":"Prior DMARD failure","weight":1.0},
      {"id":"c3","text":"TB screen negative","weight":1.0},
      {"id":"c4","text":"Specialist involvement","weight":0.8}
    ]'::jsonb,
    0.65
  ),
  (
    'UnitedHealthcare', 'semaglutide', 'GLP-1 agonist', 'E11.9', true,
    '[
      {"id":"c1","text":"Type 2 diabetes diagnosis","weight":1.0},
      {"id":"c2","text":"BMI greater than or equal to 27","weight":1.0},
      {"id":"c3","text":"Failed metformin","weight":1.0},
      {"id":"c4","text":"A1C greater than or equal to 7.0","weight":1.0}
    ]'::jsonb,
    0.60
  ),
  (
    'Aetna', 'etanercept', 'TNF inhibitor', 'M06.9', false,
    '[]'::jsonb, 0.88
  );

-- Formulary alternatives (≥2). Prefer requires_pa=false for demo.
insert into formulary_alternatives
  (payer_name, drug_class, original_drug, alternative_drug, requires_pa)
values
  ('UnitedHealthcare', 'TNF inhibitor', 'adalimumab', 'etanercept', false),
  ('UnitedHealthcare', 'GLP-1 agonist', 'semaglutide', 'dulaglutide', false),
  ('Aetna', 'TNF inhibitor', 'adalimumab', 'etanercept', false),
  ('Cigna', 'IL-4/IL-13 inhibitor', 'dupilumab', 'tralokinumab', true);
