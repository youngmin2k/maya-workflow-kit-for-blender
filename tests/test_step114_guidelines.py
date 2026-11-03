"""The two extension guideline violations of the audit stay fixed.

1. No global module dictionary / module path changes: enabling, using and disabling the kit leaves ``sys.modules``
   without any ``maya`` entry and ``sys.path`` unchanged; ``import maya.cmds`` works only inside the Command Line /
   shelf / Script Editor entries, whose import lines the runner rewrites to the kit's module (``runner.prepare``).
2. Assets: every non-code file in the package is a kit-made file listed in ``ASSETS_LICENSE.txt`` (CC0-1.0, also
   in the manifest's ``license``); the extension zip carries no legacy ``bl_info`` (the legacy zip does).
"""

import os
import re
import sys
import zipfile
from importlib import import_module

import bpy

import kit

AUTO_ENABLE = False
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "src", "allset")
CODE = {".py"}
TEXT = {"blender_manifest.toml", "LICENSE", "ASSETS_LICENSE.txt"}


def test_no_global_module_entries():
    before_mods, before_path = set(sys.modules), list(sys.path)
    kit.enable()
    try:
        runner = import_module(kit.MODULE + ".command_line.runner")
        for src in ("import maya.cmds as cmds; cmds.ls()", "from maya import cmds; cmds.ls()"):
            r = runner.run(src)
            assert not r.error, (src, r.text)
        shelf = import_module(kit.MODULE + ".ui.shelf")
        ok, msg = shelf.run_script(bpy.context, "t", "import maya.cmds as mc\nassert mc.ls is not None")
        assert ok, msg                                                  # a shelf button's script
        added = {m for m in set(sys.modules) - before_mods if m == "maya" or m.startswith("maya.")}
        assert not added, added
        assert sys.path == before_path, set(sys.path) ^ set(before_path)
        try:
            import maya.cmds  # noqa: F401  (outside the namespace: no stand-in)
            raise AssertionError("maya.cmds importable outside the kit namespace")
        except ImportError:
            pass
    finally:
        kit.disable()
    assert not any(m == "maya" or m.startswith("maya.") for m in sys.modules)


def test_no_sys_modules_writes_in_source():
    pat = re.compile(r"sys\.modules\[[^\]]+\]\s*=|sys\.modules\.(setdefault|update)\(|sys\.path\.(insert|append|extend)\(")
    hits = []
    for base, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(base, name)
                for i, line in enumerate(open(path, encoding="utf-8"), 1):
                    if pat.search(line):
                        hits.append(f"{os.path.relpath(path, PKG)}:{i}: {line.strip()}")
    assert not hits, hits


def _assets():
    out = []
    for base, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            rel = os.path.relpath(os.path.join(base, name), PKG).replace(os.sep, "/")
            if os.path.splitext(name)[1] in CODE or rel in TEXT:
                continue
            out.append(rel)
    return sorted(out)


def test_every_asset_is_kit_made_and_cc0():
    listed = open(os.path.join(PKG, "ASSETS_LICENSE.txt"), encoding="utf-8").read()
    assets = _assets()
    assert assets == ["app_template/Maya_Workflow_Kit/splash.png", "app_template/Maya_Workflow_Kit/splash_2x.png",
                      "app_template/Maya_Workflow_Kit/startup.blend", "i18n/template_en.json",
                      "welcome.png"], assets   # no theme
    for rel in assets:
        assert rel in listed, f"{rel} missing from ASSETS_LICENSE.txt"
    assert "CC0" in listed
    import tomllib
    with open(os.path.join(PKG, "blender_manifest.toml"), "rb") as fh:
        lic = tomllib.load(fh)["license"]
    assert lic == ["SPDX:GPL-3.0-or-later", "SPDX:CC0-1.0"], lic


def test_extension_zip_has_no_bl_info():
    init = open(os.path.join(PKG, "__init__.py"), encoding="utf-8").read()
    assert not re.search(r"^bl_info\s*=", init, re.M)
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        build = import_module("build")
    finally:
        sys.path.pop(0)
    version = build.manifest_value("version")
    ext = os.path.join(ROOT, "dist", f"maya-workflow-kit-{version}.zip")
    assert os.path.exists(ext), ext
    with zipfile.ZipFile(ext) as zf:
        text = zf.read("__init__.py").decode("utf-8")
        assert not re.search(r"^bl_info\s*=", text, re.M)
        assert "ASSETS_LICENSE.txt" in zf.namelist()
    tail = build.legacy_bl_info()
    ns = {}
    exec(tail, ns)
    assert ns["bl_info"]["name"] == "Maya Workflow Kit" and ns["bl_info"]["version"] == tuple(
        int(p) for p in version.split("."))
