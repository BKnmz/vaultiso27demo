"""Regression tests for the Key Personnel tab (ui/_pages/organization.py).

Covers the fix for: removing a middle person from the Key Personnel list
must never write a removed/shifted person's Role or Name onto a different,
remaining person's record (see _clear_personnel_widget_state and the
explicit "Save changes" button in _tab_personnel).

The end-to-end test drives the *real* _tab_personnel() function through
streamlit.testing.v1.AppTest (via tests/_personnel_tab_harness.py) so it
exercises the actual widget/session_state code path rather than a
reimplementation of it. ui.core.ORG_PATH is redirected to a scratch file for
the duration of each test so nothing here ever touches the real
inputs/organization_data.json.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
UI_DIR = REPO_ROOT / "ui"
HARNESS_SCRIPT = str(Path(__file__).parent / "_personnel_tab_harness.py")

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(UI_DIR))

from streamlit.testing.v1 import AppTest  # noqa: E402

THREE_PERSON_ORG = {
    "key_personnel": [
        {"role": "CEO", "name": "Alice"},
        {"role": "CISO", "name": "Bob"},
        {"role": "DPO", "name": "Carol"},
    ]
}


class TestPersonnelRemoveNoCorruption(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.org_path = self.tmpdir / "organization_data.json"
        self.org_path.write_text(json.dumps(THREE_PERSON_ORG), encoding="utf-8")

        self._env_backup = {
            k: os.environ.get(k) for k in ("VAULTISO_UI_DIR", "VAULTISO_TEST_ORG_PATH")
        }
        os.environ["VAULTISO_UI_DIR"] = str(UI_DIR)
        os.environ["VAULTISO_TEST_ORG_PATH"] = str(self.org_path)

    def tearDown(self):
        for k, v in self._env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _saved_personnel(self):
        return json.loads(self.org_path.read_text(encoding="utf-8"))["key_personnel"]

    def test_remove_middle_person_does_not_corrupt_remaining_entries(self):
        at = AppTest.from_file(HARNESS_SCRIPT)
        at.run()
        self.assertFalse(at.exception, f"initial render raised: {at.exception}")

        # Remove Bob (index 1 of [Alice, Bob, Carol]).
        at.button(key="kp_del_1").click().run()
        self.assertFalse(at.exception, f"remove raised: {at.exception}")

        # The persisted file must contain exactly Alice and Carol, with
        # Carol's own values intact — never Bob's role/name bleeding onto her.
        remaining = self._saved_personnel()
        self.assertEqual(
            remaining,
            [{"role": "CEO", "name": "Alice"}, {"role": "DPO", "name": "Carol"}],
        )

        # The re-rendered row at index 1 must show Carol's data, not a
        # stale value carried over from what used to be at that index.
        role_1 = at.text_input(key="kp_role_1").value
        name_1 = at.text_input(key="kp_name_1").value
        self.assertEqual((role_1, name_1), ("DPO", "Carol"))

        # Clicking "Save changes" immediately afterwards (e.g. a user who
        # follows Remove with an unrelated edit-and-save) must not disturb
        # Carol's record either.
        at.button(key="kp_save_edits_btn").click().run()
        self.assertFalse(at.exception, f"save raised: {at.exception}")
        self.assertEqual(
            self._saved_personnel(),
            [{"role": "CEO", "name": "Alice"}, {"role": "DPO", "name": "Carol"}],
        )

    def test_edit_persists_on_explicit_save(self):
        """The original bug this pass tried to fix: an edited Role/Name must
        actually be saved (previously only Add/Remove persisted)."""
        at = AppTest.from_file(HARNESS_SCRIPT)
        at.run()

        at.text_input(key="kp_role_0").set_value("Chief Executive Officer").run()
        # Editing alone (no Save click) must not silently write to disk.
        self.assertEqual(self._saved_personnel(), THREE_PERSON_ORG["key_personnel"])

        at.button(key="kp_save_edits_btn").click().run()
        self.assertEqual(self._saved_personnel()[0], {"role": "Chief Executive Officer", "name": "Alice"})

    def test_clear_personnel_widget_state_only_touches_kp_role_and_name_keys(self):
        """Unit test of the helper in isolation: it must drop kp_role_*/
        kp_name_* entries and nothing else."""
        sys.path.insert(0, str(UI_DIR / "_pages"))
        import streamlit as st
        import organization

        st.session_state.clear()
        st.session_state.update({
            "kp_role_0": "CEO", "kp_name_0": "Alice",
            "kp_role_1": "CISO", "kp_name_1": "Bob",
            "kp_new_role": "", "kp_new_name": "",
            "unrelated_key": "keep me",
        })
        organization._clear_personnel_widget_state()
        self.assertEqual(
            dict(st.session_state),
            {"kp_new_role": "", "kp_new_name": "", "unrelated_key": "keep me"},
        )
        st.session_state.clear()


if __name__ == "__main__":
    unittest.main()
