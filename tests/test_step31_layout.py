"""Maya Workflow Kit layout Outliner (width, Maya DAG rows) and marking-menu toggle state in the
Blender pie fallback. GUI: tests/gui/gui_step31_layout.py."""

import sys
from importlib import import_module
from pathlib import Path

import bpy

import kit

ROOT = Path(__file__).resolve().parent.parent
marking = import_module(kit.MODULE + ".marking")
mm = import_module(kit.MODULE + ".marking.menus")


def test_template_outliner_is_maya_dag():
    sys.path.insert(0, str(ROOT / "tools"))
    import make_startup
    assert make_startup.OUTLINER_PX >= 260   # Maya narrow dock width (names not cut)
    path = ROOT / "src" / "allset" / "app_template" / "Maya_Workflow_Kit" / "startup.blend"
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=True)
    screen = bpy.data.workspaces["General"].screens[0]
    outliners = [a.spaces.active for a in screen.areas if a.type == 'OUTLINER'
                 and a.spaces.active.use_filter_object]
    assert len(outliners) == 1, len(outliners)
    so = outliners[0]
    assert not so.use_filter_collection, "no collection rows (Maya DAG from the world)"
    assert not so.show_restrict_column_render
    assert not so.use_filter_object_content and so.use_filter_children


class _Layout:
    def __init__(self):
        self.icons = []

    def operator(self, idname, text="", icon='NONE'):
        self.icons.append((text, icon))
        return type("P", (), {})()


def test_pie_fallback_shows_toggle_state():
    ts = bpy.context.scene.tool_settings
    for value, icon in ((True, 'CHECKBOX_HLT'), (False, 'CHECKBOX_DEHLT')):
        ts.use_transform_correct_face_attributes = value
        lay = _Layout()
        marking.draw_entry(lay, "Preserve UVs", mm.PRESERVE_UVS, "test")
        assert lay.icons == [("Preserve UVs", icon)], lay.icons
    lay = _Layout()
    marking.draw_entry(lay, "Object Mode", ("object.mode_set", {"mode": 'OBJECT'}), "test")
    assert lay.icons == [("Object Mode", 'NONE')]
