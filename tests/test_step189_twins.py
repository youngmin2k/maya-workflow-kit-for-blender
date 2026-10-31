"""Audit 13 #10: greyed twins found through runTimeCommand aliases, panel Show rows the kit has,
Surfaces > Insert Isoparms' Maya window.
"""

from importlib import import_module
from pathlib import Path

import bpy

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")
notices = import_module(kit.MODULE + ".ui.notices")
panel_menu_data = import_module(kit.MODULE + ".ui.panel_menu_data")
panel_menus = import_module(kit.MODULE + ".ui.panel_menus")
option_windows = import_module(kit.MODULE + ".operators.option_windows")
surfaces_maya = import_module(kit.MODULE + ".operators.surfaces_maya")

ROOT = Path(__file__).resolve().parent.parent


def test_main_uv_delete_uvs_works_like_the_marking_menu():
    assert menu_map.spec("UV/Delete UVs")[1] == "allset.uv_delete"
    assert not notices.greyed_notice("UV/Delete UVs") or "UV/Delete UVs" in menu_map.MAP


def test_show_rows_for_ik_handles_and_image_planes():
    rows = {r[-1]: r for r in panel_menu_data.SHOW if r[0] != "-"}
    assert rows["IK Handles"][:2] == ("set", "SHOW_IK_HANDLES")
    assert rows["Image Planes"][:2] == ("set", "SHOW_IMAGE_PLANES")
    for label in ("IK Handles", "Image Planes"):
        assert not notices.greyed_notice(panel_menu_data.item_path("ALLSET_MT_panel_show", label)), label
    for label in ("NURBS CVs", "NURBS Hulls"):            # Blender draws control points only in Edit Mode
        assert notices.greyed_notice(panel_menu_data.item_path("ALLSET_MT_panel_show", label)), label


def test_show_ik_handles_hides_only_its_own():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    arm = bpy.data.objects.new("rig", bpy.data.armatures.new("rig"))
    bpy.context.scene.collection.objects.link(arm)
    handle = bpy.data.objects.new("ikHandle1", None)
    hidden = bpy.data.objects.new("ikHandle2", None)
    for o in (handle, hidden):
        bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for n, (h, t) in (("a", ((0, 0, 0), (0, 0, 1))), ("b", ((0, 0, 1), (0, 0, 2)))):
        b = arm.data.edit_bones.new(n)
        b.head, b.tail = h, t
    arm.data.edit_bones["b"].parent = arm.data.edit_bones["a"]
    bpy.ops.object.mode_set(mode='POSE')
    for name, target in (("b", handle), ("a", hidden)):
        con = arm.pose.bones[name].constraints.new('IK')
        con.target = target
    bpy.ops.object.mode_set(mode='OBJECT')
    hidden.hide_set(True)                                  # hidden by the user before: stays hidden
    panel_menus.show_ik_handles(bpy.context, False)
    assert handle.hide_get() and handle.get(panel_menus.SHOW_HIDDEN)
    assert hidden.get(panel_menus.SHOW_HIDDEN) is None
    panel_menus.show_ik_handles(bpy.context, True)
    assert not handle.hide_get() and handle.get(panel_menus.SHOW_HIDDEN) is None
    assert hidden.hide_get()


def test_insert_isoparms_window_and_rules():
    w = option_windows.find_path("Surfaces/Insert Isoparms")
    assert w is not None and w.title == "Insert Isoparms Options" and w.key == "surface_insert_isoparms"
    names = {f.name: f.default for f in w.fields}
    assert names == {"location": "At selection", "multiplicity": "Increase", "count": 1, "keep_original": False}
    assert surfaces_maya.between_params([0.0, 1.0], 3) == [0.25, 0.5, 0.75]
    assert surfaces_maya.between_params([0.0, 1.0, 3.0], 1) == [0.5, 2.0]

    class S:
        knots_u = [0, 0, 0, 1, 1, 2, 2, 2]
        knots_v = [0, 0, 0, 1, 1, 1]
        degree_u = degree_v = 2

    assert surfaces_maya.insert_times(S, "U", 1.0, 1, True) == 0      # already at the degree
    assert surfaces_maya.insert_times(S, "U", 1.5, 1, True) == 1
    assert surfaces_maya.insert_times(S, "U", 1.5, 3, True) == 2      # capped at the degree
    assert surfaces_maya.insert_times(S, "U", 1.0, 1, False) == 0     # Set 1: has 2
    assert surfaces_maya.insert_times(S, "V", 0.5, 2, False) == 2
