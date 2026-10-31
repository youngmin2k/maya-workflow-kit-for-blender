"""UV Editor depth 2, like Maya.
Each case rebuilds Maya's mesh (corner k of face f = loop k, vertex ids
kept), applies Maya's selection with UV sync off (the kit's UV mode), runs the kit operator and compares every
face-corner UV with the expected result."""

import json
import os
from importlib import import_module

import bpy

import kit

compat = import_module(kit.MODULE + ".compat")
mod = import_module(kit.MODULE + ".operators.uv_206")
shells_mod = import_module(kit.MODULE + ".operators.uv_shells")
uv_tools = import_module(kit.MODULE + ".operators.uv_tools")
hud = import_module(kit.MODULE + ".ui.uv_hud")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORST = {}


def _clear():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def build(verts, faces, face_uvs, name="m"):
    _clear()
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    uvl = me.uv_layers.new(name="map1")
    for f, poly in enumerate(me.polygons):
        for k in range(poly.loop_total):
            uvl.data[poly.loop_start + k].uv = face_uvs[f][k]
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    return ob


# --- Cycle --------------------------------------------------------------------------------------------------------


# --- Split --------------------------------------------------------------------------------------------------------


# --- Create Shell (Grid) ------------------------------------------------------------------------------------------


# --- Auto Seams ---------------------------------------------------------------------------------------------------


# --- HUD ----------------------------------------------------------------------------------------------------------


def test_hud_factory_on_and_menu_toggles():
    wm = bpy.context.window_manager
    for name, _l, _t in hud.PROPS:
        assert getattr(wm, name) is True, name           # default: all three HUDs shown
    emap = import_module(kit.MODULE + ".ui.editor_menu_map")
    for label, prop in (("Isolate Select", "allset_uv_hud_isolate"), ("UV Position", "allset_uv_hud_position"),
                        ("UV Statistics", "allset_uv_hud_statistics")):
        act = emap.MAP["UV Editor/View/Heads-Up Display/" + label]
        assert act[0] == "prop" and act[1] == "window_manager." + prop, act


def test_hud_format():
    assert hud.fmt(0.2) == "0.2" and hud.fmt(0.123456) == "0.123" and hud.fmt(0.165) == "0.165"
    assert hud.fmt(0.0) == "0" and hud.fmt(1.0) == "1" and hud.fmt(-0.0001) == "0"


# --- UV sets / menu -----------------------------------------------------------------------------------------------

def test_uv_sets():
    ob = build([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [(0, 1, 2, 3)], [[(0, 0), (1, 0), (1, 1), (0, 1)]])
    bpy.ops.object.mode_set(mode='OBJECT')
    layers = ob.data.uv_layers
    layers.new(name="uvSet1")
    second = layers["uvSet1"]                 # a reference kept across layers.new() crashes Blender
    layers.active = second
    for i, d in enumerate(second.data):
        d.uv = (0.5 + i * 0.1, 0.25)
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.allset.uv_set_copy_to(target="map1") == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    layers = ob.data.uv_layers
    assert [tuple(d.uv) for d in layers["map1"].data] == [tuple(d.uv) for d in layers["uvSet1"].data]
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.allset.uv_set_current(target="map1") == {'FINISHED'}
    assert ob.data.uv_layers.active.name == "map1"
    assert bpy.ops.allset.uv_set_rename('EXEC_DEFAULT', name="mainUVs") == {'FINISHED'}
    assert ob.data.uv_layers.active.name == "mainUVs"
    assert bpy.ops.allset.uv_set_current(target="map1") == {'FINISHED'}     # no map1 any more: the first set
    assert ob.data.uv_layers.active.name == "mainUVs"


def test_menu_items_mapped():
    emap = import_module(kit.MODULE + ".ui.editor_menu_map")
    for path, op in (("Cut/Sew/Auto Seams", "uv_auto_seams"), ("Cut/Sew/Create Shell (Grid)", "uv_grid_shell"),
                     ("Cut/Sew/Split", "uv_split"), ("Modify/Cycle", "uv_cycle"),
                     ("UV Sets/Rename Current UV Set...", "uv_set_rename"),
                     ("UV Sets/Copy UVs to UV Set/map1", "uv_set_copy_to"), ("UV Sets/map1", "uv_set_current")):
        act = emap.MAP["UV Editor/" + path]
        name = act if isinstance(act, str) else act[0]
        assert name == "allset." + op, (path, act)
        assert hasattr(bpy.ops.allset, op)
    notices = import_module(kit.MODULE + ".ui.notices")
    assert notices.notice("UV Editor/Modify/Warp Image")


def test_report_worst():
    print("WORST", json.dumps(WORST, indent=0, default=str))
