"""In-memory seed store — offline fallback when Supabase is unset/unreachable."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


# Canonical seeds mirror sql/seed.sql so fixtures work without Supabase.
PAYER_ALIASES: dict[str, str] = {
    "unitedhealthcare": "UnitedHealthcare",
    "uhc": "UnitedHealthcare",
    "united healthcare": "UnitedHealthcare",
    "aetna": "Aetna",
    "cigna": "Cigna",
}

DRUG_ALIASES: dict[str, dict[str, str]] = {
    "adalimumab": {"canonical_drug": "adalimumab", "drug_class": "TNF inhibitor"},
    "humira": {"canonical_drug": "adalimumab", "drug_class": "TNF inhibitor"},
    "ozempic": {"canonical_drug": "semaglutide", "drug_class": "GLP-1 agonist"},
    "semaglutide": {"canonical_drug": "semaglutide", "drug_class": "GLP-1 agonist"},
    "dupixent": {"canonical_drug": "dupilumab", "drug_class": "IL-4/IL-13 inhibitor"},
    "dupilumab": {"canonical_drug": "dupilumab", "drug_class": "IL-4/IL-13 inhibitor"},
    "enbrel": {"canonical_drug": "etanercept", "drug_class": "TNF inhibitor"},
    "etanercept": {"canonical_drug": "etanercept", "drug_class": "TNF inhibitor"},
    "trulicity": {"canonical_drug": "dulaglutide", "drug_class": "GLP-1 agonist"},
    "dulaglutide": {"canonical_drug": "dulaglutide", "drug_class": "GLP-1 agonist"},
}

# Criteria shared by Fixture B and C (UHC + adalimumab + M06.9)
UHC_ADA_RA_CRITERIA: list[dict[str, Any]] = [
    {
        "id": "c1",
        "text": "Documented diagnosis of rheumatoid arthritis",
        "weight": 1.0,
    },
    {
        "id": "c2",
        "text": "Inadequate response to methotrexate for at least 3 months",
        "weight": 1.2,
    },
    {
        "id": "c3",
        "text": "Negative TB screening within past 12 months",
        "weight": 1.0,
    },
    {
        "id": "c4",
        "text": "Prescribed by or in consultation with a rheumatologist",
        "weight": 0.8,
    },
]

PAYER_POLICIES: list[dict[str, Any]] = [
    {
        "payer_name": "Aetna",
        "drug_name": "semaglutide",
        "drug_class": "GLP-1 agonist",
        "diagnosis_code": "E11.9",
        "requires_pa": False,
        "criteria": [],
        "historical_approval_rate": 0.85,
    },
    {
        "payer_name": "UnitedHealthcare",
        "drug_name": "adalimumab",
        "drug_class": "TNF inhibitor",
        "diagnosis_code": "M06.9",
        "requires_pa": True,
        "criteria": UHC_ADA_RA_CRITERIA,
        "historical_approval_rate": 0.40,
    },
    {
        "payer_name": "UnitedHealthcare",
        "drug_name": "adalimumab",
        "drug_class": "TNF inhibitor",
        "diagnosis_code": "L40.0",
        "requires_pa": True,
        "criteria": [
            {"id": "c1", "text": "Documented diagnosis of plaque psoriasis", "weight": 1.0},
            {"id": "c2", "text": "Failed topical therapy", "weight": 1.0},
            {"id": "c3", "text": "BSA involvement greater than 10 percent", "weight": 1.0},
            {"id": "c4", "text": "Prescribed by a dermatologist", "weight": 0.8},
        ],
        "historical_approval_rate": 0.68,
    },
    {
        "payer_name": "Cigna",
        "drug_name": "dupilumab",
        "drug_class": "IL-4/IL-13 inhibitor",
        "diagnosis_code": "L20.9",
        "requires_pa": True,
        "criteria": [
            {"id": "c1", "text": "Documented moderate-to-severe atopic dermatitis", "weight": 1.0},
            {"id": "c2", "text": "Failed two topical corticosteroids", "weight": 1.0},
            {"id": "c3", "text": "IGA score of 3 or higher", "weight": 1.0},
            {"id": "c4", "text": "Prescribed by dermatology or allergy", "weight": 0.9},
        ],
        "historical_approval_rate": 0.70,
    },
    {
        "payer_name": "Cigna",
        "drug_name": "dupilumab",
        "drug_class": "IL-4/IL-13 inhibitor",
        "diagnosis_code": "J45.40",
        "requires_pa": False,
        "criteria": [],
        "historical_approval_rate": 0.90,
    },
    {
        "payer_name": "Aetna",
        "drug_name": "adalimumab",
        "drug_class": "TNF inhibitor",
        "diagnosis_code": "M06.9",
        "requires_pa": True,
        "criteria": [
            {"id": "c1", "text": "RA diagnosis confirmed", "weight": 1.0},
            {"id": "c2", "text": "Prior DMARD failure", "weight": 1.0},
            {"id": "c3", "text": "TB screen negative", "weight": 1.0},
            {"id": "c4", "text": "Specialist involvement", "weight": 0.8},
        ],
        "historical_approval_rate": 0.65,
    },
    {
        "payer_name": "UnitedHealthcare",
        "drug_name": "semaglutide",
        "drug_class": "GLP-1 agonist",
        "diagnosis_code": "E11.9",
        "requires_pa": True,
        "criteria": [
            {"id": "c1", "text": "Type 2 diabetes diagnosis", "weight": 1.0},
            {"id": "c2", "text": "BMI greater than or equal to 27", "weight": 1.0},
            {"id": "c3", "text": "Failed metformin", "weight": 1.0},
            {"id": "c4", "text": "A1C greater than or equal to 7.0", "weight": 1.0},
        ],
        "historical_approval_rate": 0.60,
    },
    {
        "payer_name": "Aetna",
        "drug_name": "etanercept",
        "drug_class": "TNF inhibitor",
        "diagnosis_code": "M06.9",
        "requires_pa": False,
        "criteria": [],
        "historical_approval_rate": 0.88,
    },
]

FORMULARY_ALTERNATIVES: list[dict[str, Any]] = [
    {
        "payer_name": "UnitedHealthcare",
        "drug_class": "TNF inhibitor",
        "original_drug": "adalimumab",
        "alternative_drug": "etanercept",
        "requires_pa": False,
    },
    {
        "payer_name": "UnitedHealthcare",
        "drug_class": "GLP-1 agonist",
        "original_drug": "semaglutide",
        "alternative_drug": "dulaglutide",
        "requires_pa": False,
    },
    {
        "payer_name": "Aetna",
        "drug_class": "TNF inhibitor",
        "original_drug": "adalimumab",
        "alternative_drug": "etanercept",
        "requires_pa": False,
    },
    {
        "payer_name": "Cigna",
        "drug_class": "IL-4/IL-13 inhibitor",
        "original_drug": "dupilumab",
        "alternative_drug": "tralokinumab",
        "requires_pa": True,
    },
]

# Runtime case store (Block 1 in-memory upsert)
_CASES: dict[str, dict[str, Any]] = {}


def normalize_key(value: str) -> str:
    return " ".join(value.strip().lower().split())


def resolve_payer(payer: str) -> str | None:
    return PAYER_ALIASES.get(normalize_key(payer))


def resolve_drug(drug: str) -> dict[str, str] | None:
    return DRUG_ALIASES.get(normalize_key(drug))


def find_policy(
    drug_name: str, diagnosis_code: str, payer_name: str
) -> dict[str, Any] | None:
    for row in PAYER_POLICIES:
        if (
            row["payer_name"] == payer_name
            and row["drug_name"] == drug_name
            and row["diagnosis_code"] == diagnosis_code
        ):
            return deepcopy(row)
    return None


def find_formulary_alternative(
    drug_class: str, payer_name: str, prefer_no_pa: bool = True
) -> dict[str, Any] | None:
    matches = [
        deepcopy(r)
        for r in FORMULARY_ALTERNATIVES
        if r["payer_name"] == payer_name and r["drug_class"] == drug_class
    ]
    if not matches:
        return None
    if prefer_no_pa:
        no_pa = [m for m in matches if not m["requires_pa"]]
        if no_pa:
            return no_pa[0]
    return matches[0]


def save_case(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _CASES[case_id] = deepcopy(payload)
    return deepcopy(_CASES[case_id])


def get_case(case_id: str) -> dict[str, Any] | None:
    row = _CASES.get(case_id)
    return deepcopy(row) if row else None


def clear_cases() -> None:
    _CASES.clear()
