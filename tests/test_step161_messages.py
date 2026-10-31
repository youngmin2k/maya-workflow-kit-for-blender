"""G1: a kit command's result goes to Maya's Command Line result field, not Blender's
status-bar report banner. Warnings / errors stay reports; tool usage hints stay Help Line reports."""

import os
import re
from importlib import import_module

import bpy

import kit

command_line = import_module(kit.MODULE + ".command_line")
results = import_module(kit.MODULE + ".results")

PKG = os.path.dirname(import_module(kit.MODULE).__file__)

# INFO reports that stay: what the mouse does in an active tool (Maya's Help Line, = Blender's status-bar banner in
# the kit layout) and the Script Editor's echo (its history is Blender's Info editor, which lists reports).
HINT_REPORTS = {
    "operators/cut_sew.py": 1,
    "operators/graph_menu_198.py": 1,     # Add Key Tool usage hint
    "operators/quad_draw.py": 3,
    "ui/script_editor.py": 1,
}


def test_no_info_report_banners_left():
    found = {}
    for root, _dirs, files in os.walk(PKG):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, PKG).replace(os.sep, "/")
            text = open(path, encoding="utf-8").read()
            n = len(re.findall(r"report\(\{'INFO'\}", text))
            if n:
                found[rel] = n
    assert found == HINT_REPORTS, found


def test_result_goes_to_the_command_line_field():
    class Op:
        def report(self, *_a):
            raise AssertionError("no Blender report for a result")
    results.result(Op(), "Result: pCube1")
    assert command_line._result == {"text": "Result: pCube1", "error": False}


def test_group_prints_maya_result():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    for o in bpy.context.scene.objects:
        o.select_set(o == ob)
    command_line._result["text"] = ""
    assert bpy.ops.allset.group() == {'FINISHED'}
    grp = bpy.context.view_layer.objects.active
    assert command_line._result["text"] == f"Result: {grp.name}", command_line._result
