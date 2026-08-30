"""Typed org profile / personnel extraction output — replaces the manual
raw.find("{")...json.loads() slicing in ui/core.py's extract_org_with_llm()
and extract_personnel_with_llm(). Fields mirror ui/core.py's ORG_JSON_SCHEMA dict
1:1 — see tests/test_org_profile_schema.py for the field-drift guard.
"""

from pydantic import BaseModel, Field


class StakeholderEntry(BaseModel):
    name: str = ""
    expectation: str = ""


class AssetEntry(BaseModel):
    name: str = ""
    system: str = ""
    owner: str = ""
    classification: str = ""


class PersonnelEntry(BaseModel):
    role: str = Field(
        default="",
        description="Job title or information-security governance role, e.g. CEO, CISO, IT Manager, DPO — NOT the person's name",
    )
    name: str = Field(
        default="",
        description="Full name of the person holding this role — NOT the job title",
    )


class OrgProfile(BaseModel):
    name: str = ""
    industry: str = ""
    size: str = ""
    scope: str = ""
    primary_processes: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    regulatory_drivers: list[str] = Field(default_factory=list)
    legal_basis: list[str] = Field(default_factory=list)
    stakeholders: list[StakeholderEntry] = Field(default_factory=list)
    assets: list[AssetEntry] = Field(default_factory=list)
    key_personnel: list[PersonnelEntry] = Field(default_factory=list)
    critical_suppliers: list[str] = Field(default_factory=list)
    existing_controls: list[str] = Field(default_factory=list)
    certifications_existing: list[str] = Field(default_factory=list)
