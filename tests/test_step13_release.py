"""Release checks that run headless (license, manifest, package contents,
first-start keymap rule). The clean-install GUI check is tools/release_check.py."""

import os
import zipfile
from importlib import import_module

import bpy

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.dirname(import_module(kit.MODULE).__file__)


def _manifest():
    with open(os.path.join(PKG, "blender_manifest.toml"), encoding="utf-8") as fh:
        return fh.read()


def test_license_files():
    with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as fh:
        root = fh.read()
    assert "GNU GENERAL PUBLIC LICENSE" in root and "Version 3, 29 June 2007" in root
    with open(os.path.join(PKG, "LICENSE"), encoding="utf-8") as fh:
        assert fh.read() == root, "src/allset/LICENSE must equal the root LICENSE"
    assert 'SPDX:GPL-3.0-or-later' in _manifest()


def test_package_contents():
    ver = next(line.split('"')[1] for line in _manifest().splitlines() if line.startswith("version"))
    path = os.path.join(ROOT, "dist", f"maya-workflow-kit-{ver}.zip")
    names = zipfile.ZipFile(path).namelist()
    assert "blender_manifest.toml" in names and "LICENSE" in names and "__init__.py" in names
    assert "app_template/Maya_Workflow_Kit/startup.blend" in names
    assert not [n for n in names if "__pycache__" in n or n.endswith((".pyc", ".blend1"))]
    # No Maya resources or research data in the package. The only
    # images are the kit's own, rendered by tools/make_splash.py.
    kit_images = {"app_template/Maya_Workflow_Kit/splash.png", "app_template/Maya_Workflow_Kit/splash_2x.png", "welcome.png"}
    assert kit_images <= set(names), kit_images - set(names)
    assert not [n for n in names if (n.rsplit(".", 1)[-1] in ("mel", "png", "xpm", "svg") and n not in kit_images)
                or "research" in n]


def test_background_enable_does_not_mark_keymap_choice():
    # `extension install-file --enable` runs in the background: the flag must stay unset so
    # the first GUI start activates the Maya keymap.
    prefs = import_module(kit.MODULE + ".preferences").get()
    assert bpy.app.background
    assert not prefs.keymap_auto_activated
    assert bpy.context.window_manager.keyconfigs.active.name == "Blender"   # never changed
