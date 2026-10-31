"""UV shell pre-selection: the shell under the mouse in the UV Editor, found among the shown faces."""
from importlib import import_module

import bmesh
import bpy
import numpy as np

import kit

pv = import_module(kit.MODULE + ".ui.uv_shell_preview")
prefs = import_module(kit.MODULE + ".preferences")


def _two_shells():
    """A 2 x 1 grid whose two faces are separate UV shells: left face at u 0..0.4, right face at u 0.6..1."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    me = bpy.data.meshes.new("grid")
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, 0.0)) for y in (0, 1) for x in (0, 1, 2)]
    left = bm.faces.new((vs[0], vs[1], vs[4], vs[3]))
    right = bm.faces.new((vs[1], vs[2], vs[5], vs[4]))
    uv = bm.loops.layers.uv.new("map1")
    for face, u0 in ((left, 0.0), (right, 0.6)):
        for lp in face.loops:
            x, y = lp.vert.co.x - face.verts[0].co.x, lp.vert.co.y
            lp[uv].uv = (u0 + 0.4 * x, y)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("grid", me)
    bpy.context.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    pv._cache.clear()
    return ob


def test_shell_under_the_mouse():
    _two_shells()
    a, faces = pv.shell_under(bpy.context, 0.2, 0.5)
    assert faces.tolist() == [0]
    a, faces = pv.shell_under(bpy.context, 0.8, 0.5)
    assert faces.tolist() == [1]
    assert pv.shell_under(bpy.context, 0.5, 0.5) is None, "between the shells: nothing"


def test_triangles_and_outline():
    _two_shells()
    a, faces = pv.shell_under(bpy.context, 0.2, 0.5)
    tris, edges = pv.shell_triangles(a, faces)
    assert tris.shape == (2, 3, 2) and edges.shape == (4, 2, 2)
    assert np.all(tris[..., 0] <= 0.4 + 1e-6)


def test_shell_mode_and_switch():
    _two_shells()
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = False
    old = ts.use_uv_select_island
    try:
        ts.use_uv_select_island = True
        assert pv.shell_mode(bpy.context)
        ts.use_uv_select_island = False
        assert not pv.shell_mode(bpy.context)
    finally:
        ts.use_uv_select_island = old
    p = prefs.get(bpy.context)
    assert p.uv_shell_preview
    p.uv_shell_preview = False
    assert not pv.enabled(bpy.context)
    p.uv_shell_preview = True


def test_hover_item_in_uv_editor():
    km = kit.maya_kc().keymaps["UV Editor"]
    items = [k for k in km.keymap_items if k.idname == "allset.uv_shell_hover" and k.active]
    assert len(items) == 1 and items[0].type == 'MOUSEMOVE'
