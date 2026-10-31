"""QA activity F, order kit_first (own Blender process): see tools/qa/qa_addons.py."""

import importlib.util
from pathlib import Path

AUTO_ENABLE = False
_spec = importlib.util.spec_from_file_location("qa_addons_body", Path(__file__).resolve().parent / "qa_addons.py")
_body = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_body)


def test_addons_kit_first():
    _body.run("kit_first")
