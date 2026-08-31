"""Standalone Streamlit script used by test_personnel_remove_no_corruption.py
via streamlit.testing.v1.AppTest.from_file().

Not a test module itself (hence no `test_` prefix — pytest must not collect
it). It renders exactly the real Key Personnel tab (ui/_pages/organization.py
_tab_personnel) against an isolated, temp-file-backed org profile so the
regression test exercises the real widget/session_state code path, not a
reimplementation of it.

Configured via two environment variables set by the test before AppTest runs:
  VAULTISO_UI_DIR       - absolute path to the repo's ui/ directory
  VAULTISO_TEST_ORG_PATH - absolute path to a scratch organization_data.json
"""
import os
import sys
from pathlib import Path

ui_dir = Path(os.environ["VAULTISO_UI_DIR"])
sys.path.insert(0, str(ui_dir))
sys.path.insert(0, str(ui_dir / "_pages"))

import core  # noqa: E402

core.ORG_PATH = Path(os.environ["VAULTISO_TEST_ORG_PATH"])

import organization  # noqa: E402

organization._tab_personnel()
