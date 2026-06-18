"""
Tests for skill template rendering with adaptive item_counts.
Verifies that Jinja2 templates correctly use min_risks, obj_range, metric_range,
min_improvements, and table_note variables passed from setup_config.TIERS.
"""

import sys
import unittest
from pathlib import Path

from jinja2 import Template, UndefinedError

sys.path.insert(0, str(Path(__file__).parent.parent))


SAMPLE_ORG = {
    "name": "Test Organization",
    "industry": "Financial Services",
    "size": "SME",
    "scope": "IT Infrastructure and Applications",
    "primary_processes": ["Payment Processing", "Customer Onboarding", "Risk Management"],
    "locations": ["New York", "London"],
    "legal_basis": ["GDPR", "PCI-DSS", "SOX"],
    "assets": ["Customer Database", "Payment Systems", "Email Systems"],
    "departments": ["IT Security", "Operations", "Compliance"],
    "regulatory_drivers": ["Payment Card Industry", "Data Protection Authority"],
}

SMALL_ITEM_COUNTS = {
    "min_risks": 3,
    "risk_range": "3-4",
    "min_objectives": 4,
    "obj_range": "4-5",
    "min_metrics": 4,
    "metric_range": "4-6",
    "min_improvements": 3,
    "table_note": " Keep tables to 3-5 rows.",
}

SKILLS_DIR = Path(__file__).parent.parent / "skills"


class TestSkillTemplateAdaptiveCounts(unittest.TestCase):
    """Test that specific skill files correctly render adaptive item_counts."""

    def _render_skill(self, filename, org=None, item_counts=None):
        """Render a single skill file with given org and item_counts."""
        if org is None:
            org = SAMPLE_ORG
        if item_counts is None:
            item_counts = {}

        skill_path = SKILLS_DIR / filename
        content = skill_path.read_text(encoding="utf-8")
        template = Template(content)

        context = {
            "org": org,
            "rag_context": "Sample RAG context for testing",
            "upstream_context": "Upstream context data",
            **item_counts,
        }
        return template.render(**context)

    def test_6_1_3_uses_min_risks(self):
        """Render 6.1.3, assert min_risks value (3) appears in output."""
        result = self._render_skill("6.1.3_risk_treatment.md", item_counts=SMALL_ITEM_COUNTS)
        self.assertIn("3", result, "min_risks value (3) should appear in rendered output")
        self.assertNotIn("create 5", result, "Old hardcoded 5 should not appear as 'create 5'")

    def test_6_1_2_uses_min_risks(self):
        """Render 6.1.2, assert min_risks value (3) appears in output."""
        result = self._render_skill("6.1.2_risk_assessment.md", item_counts=SMALL_ITEM_COUNTS)
        self.assertIn("3", result, "min_risks value (3) should appear in rendered output")

    def test_9_1_uses_metric_range(self):
        """Render 9.1, assert metric_range value (4-6) appears in output."""
        result = self._render_skill("9.1_monitoring_measurement.md", item_counts=SMALL_ITEM_COUNTS)
        self.assertIn("4-6", result, "metric_range value (4-6) should appear in rendered output")

    def test_6_2_uses_obj_range(self):
        """Render 6.2, assert obj_range value (4-5) appears in output."""
        result = self._render_skill("6.2_security_objectives.md", item_counts=SMALL_ITEM_COUNTS)
        self.assertIn("4-5", result, "obj_range value (4-5) should appear in rendered output")

    def test_10_2_uses_min_improvements(self):
        """Render 10.2, assert min_improvements values appear in output."""
        result = self._render_skill("10.2_continual_improvement.md", item_counts=SMALL_ITEM_COUNTS)
        # The template uses {{ min_improvements | default(3) }}-{{ (min_improvements | default(3)) + 1 }}
        self.assertIn("3-4", result, "min_improvements range (3-4) should appear in rendered output")

    def test_defaults_render_without_error(self):
        """Render all 5 adaptive skills WITHOUT item_counts; default() must catch undefined."""
        target_skills = [
            "6.1.3_risk_treatment.md",
            "6.1.2_risk_assessment.md",
            "9.1_monitoring_measurement.md",
            "6.2_security_objectives.md",
            "10.2_continual_improvement.md",
        ]
        for skill_file in target_skills:
            with self.subTest(skill=skill_file):
                result = self._render_skill(skill_file, item_counts={})
                self.assertTrue(result, f"{skill_file} should render non-empty output")
                self.assertGreater(len(result), 50, f"{skill_file} output should be substantial")

    def test_table_note_appended(self):
        """Render 6.1.3 with custom table_note, assert it appears in output."""
        result = self._render_skill("6.1.3_risk_treatment.md", item_counts=SMALL_ITEM_COUNTS)
        self.assertIn("Keep tables to 3-5 rows", result, "table_note should be appended to output")


class TestAllSkillsRenderWithItemCounts(unittest.TestCase):
    """Test that all 23 skill files render correctly with and without item_counts."""

    def _render_skill(self, filename, org=None, item_counts=None):
        """Render a single skill file with given org and item_counts."""
        if org is None:
            org = SAMPLE_ORG
        if item_counts is None:
            item_counts = {}

        skill_path = SKILLS_DIR / filename
        content = skill_path.read_text(encoding="utf-8")
        template = Template(content)

        context = {
            "org": org,
            "rag_context": "Sample RAG context for testing",
            "upstream_context": "Upstream context data",
            **item_counts,
        }
        return template.render(**context)

    def test_all_skills_render_with_small_counts(self):
        """Iterate all skills, render each with SAMPLE_ORG + SMALL_ITEM_COUNTS."""
        skill_files = sorted(SKILLS_DIR.glob("*.md"))
        errors = []

        for skill_path in skill_files:
            try:
                result = self._render_skill(skill_path.name, item_counts=SMALL_ITEM_COUNTS)
                self.assertTrue(result, f"{skill_path.name} should render non-empty output")
            except Exception as e:
                errors.append((skill_path.name, str(e)))

        self.assertEqual(errors, [], f"Skill rendering errors: {errors}")

    def test_all_skills_render_without_item_counts(self):
        """Iterate all skills, render each without item_counts; default() must guard."""
        skill_files = sorted(SKILLS_DIR.glob("*.md"))
        errors = []

        for skill_path in skill_files:
            try:
                result = self._render_skill(skill_path.name, item_counts={})
                self.assertTrue(result, f"{skill_path.name} should render non-empty output")
            except UndefinedError as e:
                errors.append((skill_path.name, f"UndefinedError: {str(e)}"))
            except Exception as e:
                errors.append((skill_path.name, f"Other error: {str(e)}"))

        self.assertEqual(errors, [], f"Undefined variable errors (missing default guards): {errors}")


if __name__ == "__main__":
    unittest.main()
