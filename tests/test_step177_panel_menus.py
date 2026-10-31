"""The viewport panel menus, panel toolbar and greyed Status Line widgets are counted (tools/menu_count.py),
every greyed one has a notice (menu rule), none has a working twin (tools/menu_consistency.py), and the rows with
a kit counterpart run it: Center View of Selection (Maya viewFit -c), Camera Attribute Editor, the camera
tools."""

import importlib.util
import inspect
import math
import os
import types
from importlib import import_module

import bpy
from mathutils import Vector

import kit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pmd = import_module(kit.MODULE + ".ui.panel_menu_data")
panel_menus = import_module(kit.MODULE + ".ui.panel_menus")
panel_toolbar = import_module(kit.MODULE + ".ui.panel_toolbar")
status_line = import_module(kit.MODULE + ".ui.status_line")
input_line = import_module(kit.MODULE + ".ui.input_line")
notices = import_module(kit.MODULE + ".ui.notices")
camera_tools = import_module(kit.MODULE + ".ui.camera_tools")


def _tool(name):
    spec = importlib.util.spec_from_file_location(f"tool_{name}", os.path.join(ROOT, "tools", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_greyed_panel_item_has_a_notice():
    leaves = pmd.leaves()
    greyed = {p for _f, p, ok in leaves if not ok}
    families = {f for f, _p, _ok in leaves}
    assert families == {"Panel menus", "Panel toolbar", "Status Line greys"}, families
    assert all(p.startswith((pmd.MENU_PREFIX, pmd.TOOLBAR_PREFIX, "Status Line/")) for p in greyed)
    missing = sorted(p for p in greyed if not notices.greyed_notice(p))
    assert not missing, missing
    unused = sorted(k for k in notices.PANEL_MENU if k not in greyed)     # a notice for an item that works / is gone
    assert not unused, unused
    # the tooltip of a greyed panel row is its notice, not the generic "No Blender equivalent" text
    tip = notices.tooltip(pmd.MENU_PREFIX + "Shading/Flat Shade All", mapped=False)
    assert tip and "Use Flat Lighting" in tip, tip


def test_drawn_rows_are_the_counted_rows():
    # the menus draw the data module's tables; greyed rows carry the counted path
    assert panel_menus.VIEW is pmd.VIEW and panel_menus.SHOW is pmd.SHOW and panel_toolbar.TOOLBAR is pmd.TOOLBAR
    assert pmd.item_path("ALLSET_MT_panel_camera_tools", "2D Pan/Zoom Tool") == \
        "Panel menu/View/Camera Tools/2D Pan∕Zoom Tool"
    assert "item_path(idname, row[1])" in inspect.getsource(panel_menus.draw_rows)
    # every generated panel menu has a path (its greyed rows are named by it)
    for cls in panel_menus._generated:
        assert cls.bl_idname in pmd.MENUS, cls.bl_idname
    # Status Line: the greyed widgets it draws are the listed ones
    drawn = {f"Status Line/{desc}" for _g, desc, _i, types_ in status_line.OBJECT_MASKS if types_ is None}
    drawn |= {f"Status Line/{desc}" for _n, desc, _i, el in status_line.SNAPS if el is None}
    assert input_line.HISTORY_PATH not in pmd.STATUS_LINE      # a real toggle
    src = inspect.getsource(status_line)
    drawn |= {p for p in pmd.STATUS_LINE if f'"{p}"' in src}
    assert drawn == set(pmd.STATUS_LINE), drawn ^ set(pmd.STATUS_LINE)


def test_menu_count_prints_panel_rows():
    mc = _tool("menu_count")
    md = types.SimpleNamespace(MENU_SETS=import_module(kit.MODULE + ".ui.menu_data").MENU_SETS,
                               MENUS=import_module(kit.MODULE + ".ui.menu_data").MENUS,
                               EDITORS=import_module(kit.MODULE + ".ui.editor_menu_data").EDITORS, PANEL=pmd)
    r = mc.count(md, import_module(kit.MODULE + ".ui.menu_map"), notices)
    panels = r["panels"]
    print("panel rows", {k: dict(v) for k, v in panels.items()})
    assert set(panels) == {"Panel menus", "Panel toolbar", "Status Line greys"}
    for c in panels.values():
        assert c["greyed"] == 0 and c["leaves"] == c["working"] + c["greyed+notice"]
    assert panels["Panel menus"]["working"] >= 67 and panels["Panel toolbar"]["working"] >= 22


def test_connected_rows():
    rows = {r[1]: r for r in pmd.VIEW + pmd.CAMERA_TOOLS if r[0] in ("run", "grey")}
    assert rows["Center View of Selection"][2] == "allset.center_view_selection"
    assert rows["Camera Attribute Editor..."][2] == "allset.camera_attribute_editor"
    for label, tool in (("Tumble Tool", camera_tools.TUMBLE_TOOL), ("Track Tool", camera_tools.TRACK_TOOL),
                        ("Dolly Tool", camera_tools.DOLLY_TOOL), ("Grease Pencil Tool", "builtin.annotate")):
        assert rows[label][2] == "wm.tool_set_by_id" and rows[label][3] == {"name": tool}, label
    cam_attr = next(it for g in pmd.TOOLBAR for it in g if it[0] == "cam_attr")
    assert cam_attr[1] == "run" and cam_attr[2][0] == "allset.camera_attribute_editor"
    for op in ("center_view_selection", "camera_attribute_editor", "track"):
        assert hasattr(bpy.types, f"ALLSET_OT_{op}"), op
    # the camera tools are registered in object and mesh edit mode, LMB drag = tumble / track / dolly
    ops = {t.bl_idname: t.bl_keymap[0][0] for t in camera_tools.TOOLS}
    assert ops == {camera_tools.TUMBLE_TOOL: "allset.tumble", camera_tools.TRACK_TOOL: "allset.track",
                   camera_tools.DOLLY_TOOL: "allset.dolly"}
    assert {t.bl_context_mode for t in camera_tools.TOOLS} == {'OBJECT', 'EDIT_MESH'}
    tools = bpy.types.VIEW3D_PT_tools_active._tools
    for mode in ('OBJECT', 'EDIT_MESH'):
        ids = set()
        for t in tools[mode]:          # ToolDefs (namedtuples), groups (tuples of ToolDefs), None, callables
            for x in ((t,) if hasattr(t, "idname") else t if isinstance(t, tuple) else ()):
                ids.add(getattr(x, "idname", None))
        assert camera_tools.TUMBLE_TOOL in ids, (mode, sorted(i for i in ids if i))


def test_center_view_rule_matches_maya():
    # Maya persp at (28, 21, 28), rotate (-27.9384, 45, 0) (Y-up), cube centre
    # (5, 2, -3) -> viewFit -c moves the camera to (31.8764, 22.1573, 23.8764), rotation kept, COI 43.0232.
    rx, ry = math.radians(-27.9384), math.radians(45.0)
    forward = Vector((-math.sin(ry) * math.cos(rx), math.sin(rx), -math.cos(ry) * math.cos(rx)))
    eye, dist = camera_tools.centre_view((28, 21, 28), forward, (5, 2, -3))
    assert (eye - Vector((31.8764, 22.1573, 23.8764))).length < 1e-3, eye
    assert abs(dist - 43.0232) < 1e-3, dist
    assert camera_tools.bbox_centre([(0, 0, 0), (2, 4, -6), (1, 1, 1)]) == Vector((1, 2, -2.5))


def test_center_view_keeps_a_camera_rotation():
    # Through a camera: the camera keeps its rotation and its distance to the selection, which ends on its view axis
    scene = bpy.context.scene
    cam = bpy.data.objects.new("cam177", bpy.data.cameras.new("cam177"))
    scene.collection.objects.link(cam)
    cam.location = (0.0, -10.0, 0.0)
    cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    bpy.context.view_layer.update()
    eye, d = camera_tools.centre_view(cam.location, cam.matrix_world.to_quaternion() @ Vector((0, 0, -1)), (3, 0, 4))
    assert abs(d - math.dist((0, -10, 0), (3, 0, 4))) < 1e-6
    # the new eye looks straight at the centre
    fwd = cam.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    to_c = (Vector((3, 0, 4)) - eye).normalized()
    assert (to_c - fwd).length < 1e-6
