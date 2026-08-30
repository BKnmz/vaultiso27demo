"""
Tests for launch.py's _ollama_version_supports_structured_output() — advisory check
that the local Ollama is new enough (0.5.0+) for grammar-constrained JSON output.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import launch


class TestOllamaVersionSupportsStructuredOutput(unittest.TestCase):
    def test_current_version_supported(self):
        self.assertTrue(launch._ollama_version_supports_structured_output("0.30.10"))

    def test_exact_minimum_version_supported(self):
        self.assertTrue(launch._ollama_version_supports_structured_output("0.5.0"))

    def test_older_version_unsupported(self):
        self.assertFalse(launch._ollama_version_supports_structured_output("0.4.9"))

    def test_much_older_version_unsupported(self):
        self.assertFalse(launch._ollama_version_supports_structured_output("0.1.0"))

    def test_unparseable_version_fails_open(self):
        # Advisory only — never block startup just because the version string was odd.
        self.assertTrue(launch._ollama_version_supports_structured_output("weird-build"))

    def test_empty_string_fails_open(self):
        self.assertTrue(launch._ollama_version_supports_structured_output(""))


class TestCheckHardwareConfigNonInteractive(unittest.TestCase):
    def test_auto_repair_passes_non_interactive_flag(self):
        # Regression test: check_hardware_config() runs setup_config.py as an
        # unattended background subprocess with no stdin the user is watching.
        # setup_config.py's main() now calls input() when run interactively -
        # this subprocess call must always pass --non-interactive, or an
        # unattended launch can hang forever waiting for a keystroke.
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "config.yaml"
            cfg_path.write_text("llm:\n  model: x\n", encoding="utf-8")  # no "timeouts" key
            mock_result = MagicMock(returncode=0)
            with patch("launch.BASE_DIR", Path(tmpdir)), \
                 patch("launch.subprocess.run", return_value=mock_result) as mock_run:
                launch.check_hardware_config()
            called_args = mock_run.call_args[0][0]
            self.assertIn("--non-interactive", called_args)


if __name__ == "__main__":
    unittest.main(verbosity=2)
