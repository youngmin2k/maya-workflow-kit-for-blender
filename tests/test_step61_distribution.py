"""The package stays within the Extensions platform rules that can be checked offline.

Rules: manifest fields (https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html —
tagline / permission reasons <= 64 chars without end punctuation, tags from the platform list, optional
fields non-empty when present), Terms of Service 2.1 (no "Blender" in the name), 1.1 (GPL-3.0-or-later),
moderation checklist (no auto-updater / network code, no hard-coded repository names; writable data in
``extension_path_user``).
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "src", "allset")


def _manifest():
    import tomllib
    with open(os.path.join(PKG, "blender_manifest.toml"), "rb") as fh:
        return tomllib.load(fh)


def _sources():
    for base, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(base, name)
                with open(path, encoding="utf-8") as fh:
                    yield os.path.relpath(path, PKG).replace(os.sep, "/"), fh.read()


def _code_lines(text):
    """Source lines without comments (docstrings may mention names; code may not)."""
    for line in text.splitlines():
        code = line.split("#", 1)[0]
        if code.strip():
            yield code


def test_manifest_fields():
    m = _manifest()
    assert "blender" not in m["name"].lower(), "ToS 2.1: no 'Blender' in the extension name"
    assert m["license"] == ["SPDX:GPL-3.0-or-later", "SPDX:CC0-1.0"], m["license"]   # code GPL, kit-made assets CC0
    tagline = m["tagline"]
    assert len(tagline) <= 64 and tagline[-1] not in ".!?,;:", tagline
    for key, reason in m.get("permissions", {}).items():
        assert key in ("files", "network", "clipboard", "camera", "microphone"), key
        assert reason and len(reason) <= 64 and reason[-1] not in ".!?,;:", (key, reason)
    from _bpy_internal.extensions.tags import addons as valid_tags
    assert m["tags"] and set(m["tags"]) <= valid_tags, set(m["tags"]) - valid_tags
    for key in ("website", "copyright", "platforms", "tags"):
        if key in m:
            assert m[key], f"optional field {key} must be left out rather than empty"
    assert "network" not in m.get("permissions", {}), "the kit has no network code"


def test_no_network_or_self_update():
    bad = []
    for rel, text in _sources():
        for code in _code_lines(text):
            if re.search(r"\b(import|from)\s+(urllib|http|requests|socket|ssl|ftplib)\b", code):
                bad.append((rel, code.strip()))
    assert not bad, f"network code (moderation: no auto-updater, ToS 4): {bad}"


def test_no_hard_coded_repository_names():
    bad = []
    for rel, text in _sources():
        for code in _code_lines(text):
            if re.search(r"""["'](bl_ext\.|user_default|blender_org)""", code):
                bad.append((rel, code.strip()))
    assert not bad, f"use __package__, not repository names (moderation checklist): {bad}"


def test_writes_outside_the_extension_folder_are_known():
    """Writable data goes to bpy.utils.extension_path_user only. The layout file is never copied out
    of the extension (no app template), the switch keeps no snapshot and the shelf's legacy-build fallback is a
    folder inside the add-on (#42): no user_resource() call is left. A new one must be reviewed first."""
    known = set()
    found = {rel for rel, text in _sources()
             if any("user_resource(" in code for code in _code_lines(text))}
    assert found <= known, f"new write location outside extension_path_user: {sorted(found - known)}"
    for rel in found:
        text = dict(_sources())[rel]
        assert "extension_path_user" in text and re.search(r"except \(?ValueError", text), \
            f"{rel}: CONFIG must stay the legacy-build fallback only"
