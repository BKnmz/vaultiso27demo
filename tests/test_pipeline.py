"""
Tests for pipeline.py — prompt rendering, caching, status, upstream context.
Ollama is mocked — no real LLM calls.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pipeline


BASE_DIR = Path(__file__).parent.parent

SAMPLE_ORG = {
    "name": "Test Corp",
    "industry": "Testing",
    "size": "10 employees",
    "scope": "Test scope",
    "primary_processes": ["Process A"],
    "assets": [{"name": "Server", "system": "Linux", "owner": "IT", "classification": "Internal"}],
    "legal_basis": ["GDPR"],
    "stakeholders": [{"name": "Client", "expectation": "Security"}],
    "locations": ["Istanbul"],
    "key_personnel": [{"role": "CEO", "name": "Jane"}],
    "critical_suppliers": [],
    "existing_controls": ["MFA"],
    "certifications_existing": [],
}


class TestSkillFilename(unittest.TestCase):
    def test_known_clauses(self):
        cases = {
            "4.1": "4.1_context_of_organization.md",
            "6.1.2": "6.1.2_risk_assessment.md",
            "10.2": "10.2_continual_improvement.md",
        }
        for cid, expected in cases.items():
            self.assertEqual(pipeline.skill_filename(cid), expected)

    def test_unknown_clause_returns_none(self):
        self.assertIsNone(pipeline.skill_filename("99.9"))


class TestContentHash(unittest.TestCase):
    def test_same_inputs_same_hash(self):
        h1 = pipeline.content_hash("hello", "world")
        h2 = pipeline.content_hash("hello", "world")
        self.assertEqual(h1, h2)

    def test_different_inputs_different_hash(self):
        h1 = pipeline.content_hash("hello", "world")
        h2 = pipeline.content_hash("hello", "changed")
        self.assertNotEqual(h1, h2)

    def test_returns_string(self):
        self.assertIsInstance(pipeline.content_hash("test"), str)


class TestUpstreamContext(unittest.TestCase):
    def test_no_files_returns_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = pipeline.build_upstream_context("5.2", Path(tmpdir))
            self.assertIn("No upstream context", result)

    def test_picks_up_existing_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "4.1.md").write_text("This is the context of the organization document.")
            result = pipeline.build_upstream_context("4.2", tmppath)
            self.assertIn("4.1", result)
            self.assertIn("context", result.lower())

    def test_truncates_to_max_chars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            long_text = "X" * 1000
            (tmppath / "4.1.md").write_text(long_text)
            result = pipeline.build_upstream_context("4.2", tmppath)
            # Should be truncated to MAX_UPSTREAM_CHARS
            self.assertLessEqual(len(result), pipeline.MAX_UPSTREAM_CHARS + 100)

    def test_upstream_map_completeness(self):
        # All clauses in upstream map should reference valid clause IDs
        all_clauses = set(pipeline.skill_filename(cid) and cid for cid in [
            "4.1","4.2","4.3","5.1","5.2","5.3","6.1","6.1.2","6.1.3","6.2",
            "7.1","7.2","7.3","7.4","7.5","8.1","8.2","8.3","9.1","9.2","9.3","10.1","10.2"
        ])
        for clause, upstream_list in pipeline.UPSTREAM_MAP.items():
            for uid in upstream_list:
                self.assertIn(uid, all_clauses, f"Unknown upstream ref {uid} for {clause}")


class TestPromptRendering(unittest.TestCase):
    def test_skill_template_renders_org_name(self):
        from jinja2 import Template
        skill_path = BASE_DIR / "skills" / "4.3_scope.md"
        if not skill_path.exists():
            self.skipTest("Skill file not found")

        template = Template(skill_path.read_text(encoding="utf-8"))
        rendered = template.render(
            clause_id="4.3",
            org=SAMPLE_ORG,
            rag_context="Test RAG context",
            upstream_context="No upstream",
        )
        self.assertIn("Test Corp", rendered)
        self.assertIn("4.3", rendered)
        self.assertIn("Test RAG context", rendered)

    def test_all_skill_files_render_without_error(self):
        from jinja2 import Template
        skills_dir = BASE_DIR / "skills"
        errors = []
        for skill_file in skills_dir.glob("*.md"):
            try:
                tmpl = Template(skill_file.read_text(encoding="utf-8"))
                tmpl.render(
                    clause_id="X.X",
                    org=SAMPLE_ORG,
                    rag_context="RAG",
                    upstream_context="Upstream",
                )
            except Exception as e:
                errors.append(f"{skill_file.name}: {e}")
        self.assertEqual(errors, [], f"Template render errors: {errors}")


class TestOutputCache(unittest.TestCase):
    def test_cache_hit_skips_generation(self):
        """If hash matches, generate_clause should return True without calling Ollama."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir)
            cfg = {
                "llm": {"base_url": "http://localhost:11434", "model": "test", "temperature": 0.2},
                "rag": {"top_k": 3, "chroma_db_path": "rag/chroma_db", "collection_name": "iso27001"},
                "paths": {"outputs": str(outputs_dir), "skills": str(BASE_DIR / "skills")},
                "critic": {"enabled": False, "auto_clauses": []},
            }

            # Pre-write a cached output and matching hash
            clause_id = "4.3"
            rag_ctx = "cached rag"
            skill_text = (BASE_DIR / "skills" / "4.3_scope.md").read_text(encoding="utf-8")
            h = pipeline.content_hash(json.dumps(SAMPLE_ORG, sort_keys=True), rag_ctx, skill_text)

            (outputs_dir / f"{clause_id}.md").write_text("Cached document content")
            (outputs_dir / f"{clause_id}.hash").write_text(h)

            mock_collection = MagicMock()
            mock_embed = MagicMock()

            with patch("pipeline.get_rag_context", return_value=rag_ctx), \
                 patch("pipeline.call_ollama") as mock_ollama:
                result = pipeline.generate_clause(
                    clause_id, cfg, SAMPLE_ORG,
                    mock_collection, mock_embed, force=False
                )
                mock_ollama.assert_not_called()
                self.assertTrue(result)

    def test_force_bypasses_cache(self):
        """--force should call Ollama even if hash matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs_dir = Path(tmpdir)
            cfg = {
                "llm": {"base_url": "http://localhost:11434", "model": "test", "temperature": 0.2},
                "rag": {"top_k": 3, "chroma_db_path": "rag/chroma_db", "collection_name": "iso27001"},
                "paths": {"outputs": str(outputs_dir), "skills": str(BASE_DIR / "skills")},
                "critic": {"enabled": False, "auto_clauses": []},
            }

            clause_id = "4.3"
            skill_text = (BASE_DIR / "skills" / "4.3_scope.md").read_text(encoding="utf-8")
            rag_ctx = "forced rag"
            h = pipeline.content_hash(json.dumps(SAMPLE_ORG, sort_keys=True), rag_ctx, skill_text)

            (outputs_dir / f"{clause_id}.md").write_text("Old content")
            (outputs_dir / f"{clause_id}.hash").write_text(h)

            mock_collection = MagicMock()
            mock_embed = MagicMock()

            with patch("pipeline.get_rag_context", return_value=rag_ctx), \
                 patch("pipeline.call_ollama", return_value="New generated content") as mock_ollama:
                result = pipeline.generate_clause(
                    clause_id, cfg, SAMPLE_ORG,
                    mock_collection, mock_embed, force=True
                )
                mock_ollama.assert_called_once()
                self.assertTrue(result)
                self.assertEqual(
                    (outputs_dir / f"{clause_id}.md").read_text(),
                    "New generated content"
                )


class TestOllamaConnectionError(unittest.TestCase):
    def test_connection_error_raises_system_exit(self):
        import requests
        with self.assertRaises(SystemExit):
            pipeline.call_ollama("http://localhost:9999", "model", "prompt")


class TestRevisionLoop(unittest.TestCase):
    def _make_cfg(self, outputs_dir, max_revisions=2):
        return {
            "llm": {"base_url": "http://localhost:11434", "model": "test", "temperature": 0.2},
            "rag": {"top_k": 3, "chroma_db_path": "rag/chroma_db", "collection_name": "iso27001"},
            "paths": {"outputs": str(outputs_dir), "skills": str(BASE_DIR / "skills")},
            "critic": {"enabled": True, "model": "qwen2.5:1.5b", "temperature": 0.1,
                       "max_revisions": max_revisions, "auto_clauses": ["4.3"]},
        }

    def test_stops_on_pass(self):
        """Loop should stop after first PASS and not call Ollama for revision."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "4.3.md"
            out_file.write_text("Draft content", encoding="utf-8")

            cfg = self._make_cfg(Path(tmpdir))

            with patch("critic.run_critic", return_value=("PASS", "## Critic\n**Overall Assessment:** PASS")) as mock_critic, \
                 patch("pipeline.call_ollama") as mock_ollama:
                result = pipeline.run_revision_loop("4.3", cfg, SAMPLE_ORG, out_file, max_revisions=2)

            self.assertEqual(result, "PASS")
            mock_critic.assert_called_once()
            mock_ollama.assert_not_called()

    def test_revises_on_fail_then_passes(self):
        """Loop should call Ollama once for revision when critic returns FAIL then PASS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "4.3.md"
            out_file.write_text("Draft content", encoding="utf-8")

            cfg = self._make_cfg(Path(tmpdir))

            fail_text = (
                "## Critic\n**Overall Assessment:** FAIL\n"
                "### Findings Table\n| 1 | ISO Mapping | FAIL | Missing items |\n"
                "### Required Revisions\n- Fix section 2\n"
            )
            critic_side_effects = [("FAIL", fail_text), ("PASS", "## Critic\n**Overall Assessment:** PASS")]

            with patch("critic.run_critic", side_effect=critic_side_effects) as mock_critic, \
                 patch("pipeline.call_ollama", return_value="Revised content") as mock_ollama:
                result = pipeline.run_revision_loop("4.3", cfg, SAMPLE_ORG, out_file, max_revisions=2)

            self.assertEqual(result, "PASS")
            self.assertEqual(mock_critic.call_count, 2)
            mock_ollama.assert_called_once()
            self.assertEqual(out_file.read_text(encoding="utf-8"), "Revised content")

    def test_stops_at_max_revisions(self):
        """Loop should stop after max_revisions even if critic keeps returning FAIL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "4.3.md"
            out_file.write_text("Draft content", encoding="utf-8")

            cfg = self._make_cfg(Path(tmpdir), max_revisions=2)

            fail_text = (
                "## Critic\n**Overall Assessment:** FAIL\n"
                "### Required Revisions\n- Fix everything\n"
            )

            with patch("critic.run_critic", return_value=("FAIL", fail_text)) as mock_critic, \
                 patch("pipeline.call_ollama", return_value="Still not great") as mock_ollama:
                result = pipeline.run_revision_loop("4.3", cfg, SAMPLE_ORG, out_file, max_revisions=2)

            self.assertEqual(result, "FAIL")
            # max_revisions=2: critic called twice, Ollama called once (second critic stops loop)
            self.assertEqual(mock_critic.call_count, 2)
            self.assertEqual(mock_ollama.call_count, 1)


class TestExtractCriticFindings(unittest.TestCase):
    def test_extracts_findings_table_and_revisions(self):
        critic_text = (
            "## Critic Review\n**Overall Assessment:** FAIL\n\n"
            "### Findings Table\n| 1 | ISO Mapping | FAIL | Detail |\n\n"
            "### Required Revisions\n- Fix X\n- Fix Y\n\n"
            "### Auditor Verdict\nNeeds work.\n"
        )
        result = pipeline.extract_critic_findings(critic_text)
        self.assertIn("Findings Table", result)
        self.assertIn("Required Revisions", result)
        self.assertIn("Fix X", result)

    def test_falls_back_to_truncated_text_when_no_sections(self):
        critic_text = "Some plain text without expected sections. " * 50
        result = pipeline.extract_critic_findings(critic_text)
        self.assertLessEqual(len(result), 1500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
