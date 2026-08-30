"""
Tests for schemas/org_profile.py — OrgProfile / PersonnelEntry structural guarantees,
and the field-drift guard against ui/core.py's legacy ORG_JSON_SCHEMA dict.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas.org_profile import AssetEntry, OrgProfile, PersonnelEntry, StakeholderEntry


class TestOrgProfileDefaults(unittest.TestCase):
    def test_all_fields_default_without_arguments(self):
        # Downstream code does unconditional org.get(key, []) with no None-checks —
        # every field must have a usable default, never None.
        profile = OrgProfile()
        self.assertEqual(profile.name, "")
        self.assertEqual(profile.primary_processes, [])
        self.assertEqual(profile.stakeholders, [])
        self.assertEqual(profile.assets, [])
        self.assertEqual(profile.key_personnel, [])

    def test_no_field_is_optional_none(self):
        for field in OrgProfile.model_fields.values():
            self.assertNotIn("NoneType", str(field.annotation))

    def test_nested_entries_construct(self):
        profile = OrgProfile(
            name="Acme",
            stakeholders=[StakeholderEntry(name="Regulator", expectation="Compliance")],
            assets=[AssetEntry(name="ERP", system="SAP", owner="IT", classification="Confidential")],
            key_personnel=[PersonnelEntry(role="CEO", name="Jane Doe")],
        )
        self.assertEqual(profile.stakeholders[0].expectation, "Compliance")
        self.assertEqual(profile.assets[0].system, "SAP")
        self.assertEqual(profile.key_personnel[0].name, "Jane Doe")

    def test_model_dump_round_trips_to_plain_dict(self):
        profile = OrgProfile(name="Acme", locations=["Berlin"])
        dumped = profile.model_dump()
        self.assertIsInstance(dumped, dict)
        self.assertEqual(dumped["name"], "Acme")
        self.assertEqual(dumped["locations"], ["Berlin"])


class TestOrgProfileMatchesLegacySchema(unittest.TestCase):
    def test_fields_match_legacy_org_json_schema_keys(self):
        # Field-drift guard: if a future session adds a field to one but not the
        # other, this fails loudly instead of silently diverging.
        sys.path.insert(0, str(Path(__file__).parent.parent / "ui"))
        import core

        self.assertEqual(set(OrgProfile.model_fields.keys()), set(core.ORG_JSON_SCHEMA.keys()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
