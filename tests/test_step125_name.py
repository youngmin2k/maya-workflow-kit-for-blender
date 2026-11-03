"""The product is "Maya Workflow Kit" — manifest name, layout folder, zip name, no user-visible "Allset"
left in the package. (There is no app template install / legacy-copy cleanup.)"""

import os
import re
import sys
from importlib import import_module

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "allset")
# Hidden identifiers users never see (leading-dot data names, a PropertyGroup class name).
HIDDEN = (".Allset Tension", ".Allset Solidify", ".Allset Sculpt", ".Allset Morph", ".Allset Jiggle", ".AllsetList", ".AllsetStrip", ".AllsetShelf", ".Allset Smooth Preview Shading", ".Allset Wire", ".Allset Sweep Mesh", ".Allset Weight Sum", ".Allset Type", '".Allset"', "AllsetNucleus", '"Allset"',
          # helper collections, linked to no scene (never in a View Layer Outliner)
          ".AllsetConstraintHelpers", ".AllsetControlShapes", ".AllsetPoseHelpers")


def _mod(name):
    return import_module(f"{kit.MODULE}.{name}")


def test_manifest_and_constants():
    text = open(os.path.join(SRC, "blender_manifest.toml"), encoding="utf-8").read()
    assert re.search(r'^name = "Maya Workflow Kit"$', text, re.M)
    assert re.search(r'^id = "allset"$', text, re.M), "the extension id stays allset"
    tagline = re.search(r'^tagline = "([^"]+)"$', text, re.M).group(1)
    assert tagline == "The whole Maya workflow in Blender, in one install"
    assert len(tagline) <= 64 and not tagline.endswith(".")
    assert _mod("names").PRODUCT == "Maya Workflow Kit"
    app_template = _mod("app_template")
    assert app_template.TEMPLATE_ID == "Maya_Workflow_Kit" and os.path.isdir(app_template.SOURCE_DIR)


def test_zip_name():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        build = import_module("build")
    finally:
        sys.path.pop(0)
    version = build.manifest_value("version")
    assert build.ext_zip().name == f"maya-workflow-kit-{version}.zip"
    assert build.legacy_zip().name == f"maya-workflow-kit-{version}-legacy.zip"


def test_no_allset_in_user_visible_text():
    hits = []
    for folder, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if not name.endswith((".py", ".toml", ".txt")):
                continue
            path = os.path.join(folder, name)
            for n, line in enumerate(open(path, encoding="utf-8"), 1):
                for h in HIDDEN:
                    line = line.replace(h, "")
                if "Allset" in line:
                    hits.append(f"{os.path.relpath(path, SRC)}:{n}: {line.strip()}")
    assert not hits, "\n".join(hits)
