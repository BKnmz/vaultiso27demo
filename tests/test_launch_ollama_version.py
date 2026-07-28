"""
Tests for launch.py's _ollama_version_supports_structured_output() — advisory check
that the local Ollama is new enough (0.5.0+) for grammar-constrained JSON output.
"""

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
