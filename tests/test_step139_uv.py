"""Lane UV (#68): UV > Automatic / Contour Stretch from object mode act on the whole
object, Automatic = Maya polyAutoProjection (expected shell counts), UV Editor > Create > Best Plane / Contour Stretch
mapped like the main UV menu.
GUI: tests/gui/gui_step139_uv.py."""

from importlib import import_module

import bmesh
import bpy

import kit

uvt = import_module(kit.MODULE + ".operators.uv_tools")
ow = import_module(kit.MODULE + ".operators.option_windows")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
menu_sets = import_module(kit.MODULE + ".ui.menu_sets")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    ow.store("uv_automatic", None)


def _make(kind):
    _clear()
    bpy.ops.allset.create(kind=kind)
    ob = bpy.context.active_object
    if ob.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.scene.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    return ob


def _info(ob):
    """(shells, faces per shell, UV count, UV bounds) of ``ob``'s active UV map; UV count = Maya's (one per distinct
    (vertex, UV position))."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    shells = uvt.islands(bm, uv)
    uvs = {(lp.vert.index, round(lp[uv].uv.x, 4), round(lp[uv].uv.y, 4)) for f in bm.faces for lp in f.loops}
    pts = [lp[uv].uv for f in bm.faces for lp in f.loops]
    bounds = (min(p.x for p in pts), min(p.y for p in pts), max(p.x for p in pts), max(p.y for p in pts))
    out = (len(shells), sorted((len(s) for s in shells), reverse=True), len(uvs), bounds)
    bm.free()
    return out


def test_planes_option_and_window():
    w = ow.find_path("UV/Automatic")
    assert w is not None and w.key == "uv_automatic"
    assert ow.find_path("UV Editor/Create/Automatic") is w          # the UV Editor item has the same option box
    ob = _make('CUBE')
    res = ow.run(w, bpy.context, {"planes": "4", "spacing": 0.2})
    assert res == {'FINISHED'}, res
    n, _g, _c, _b = _info(ob)
    assert 2 <= n <= 6, n                 # Maya 4 planes on a cube: 4 shells; kit: tetrahedron planes
    for planes in ("3", "5", "8", "12"):
        _make('SPHERE')
        assert bpy.ops.allset.uv_automatic(planes=planes) == {'FINISHED'}


def test_uv_editor_create_items_mapped():
    """U2: UV Editor > Create > Best Plane / Contour Stretch run the main UV menu's actions."""
    for item, main in (("Best Plane", "UV/Best Plane"), ("Contour Stretch", "UV/Contour Stretch"),
                       ("Automatic", "UV/Automatic")):
        path = f"UV Editor/Create/{item}"
        assert path in menu_map.MAP, path
        assert menu_map.spec(path) == menu_map.spec(main), (path, menu_map.spec(path), menu_map.spec(main))
    ob = _make('CUBE')
    assert bpy.ops.allset.menu_item(item="UV Editor/Create/Best Plane") == {'FINISHED'}
    assert bpy.ops.allset.menu_item(item="UV Editor/Create/Contour Stretch") == {'FINISHED'}
    assert ob.data.uv_layers.active is not None


def test_blender_alternatives_recorded():
    """Record what Blender's own operators give on the same objects (why the kit projects in bmesh)."""
    out = {}
    for kind in ('CUBE', 'SPHERE'):
        ob = _make(kind)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.002)      # 66 degrees
        bpy.ops.object.mode_set(mode='OBJECT')
        out[kind + " smart_project"] = _info(ob)[:2]
    print("Blender alternatives:", {k: (v[0], v[1][:8]) for k, v in out.items()})


def test_other_projections_from_object_mode():
    """Maya's Planar / Cylindrical / Spherical also take an object selection as all its faces."""
    for item in ("UV/Planar", "UV/Normal-Based", "UV/Best Plane", "UV/Cylindrical", "UV/Spherical"):
        ob = _make('CUBE')
        before = _info(ob)
        assert bpy.ops.allset.menu_item(item=item) == {'FINISHED'}, item
        assert bpy.context.mode == 'OBJECT'
        after = _info(ob)
        print(item, before[:3], "->", after[:3])
        assert after[2:] != before[2:], item      # the UVs changed
