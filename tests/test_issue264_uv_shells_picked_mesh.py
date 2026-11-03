"""UV shell commands with several meshes in edit mode: when shells are picked on one mesh only, Stack, Orient,
Distribute, Unstack, Layout Along and Stack Similar work on those shells and leave the other mesh's UVs alone
(all shells are used only when nothing is picked anywhere)."""

import math

import bmesh
import bpy

import kit  # noqa: F401  (enables the kit)

OPS = ("uv_stack", "uv_orient_shells", "uv_distribute", "uv_unstack", "uv_layout_along", "uv_stack_similar")


def _two_shells(name, x0):
    """A mesh of two separate quads; each is its own UV shell, the second one turned 30 degrees."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("map1")
    for k in range(2):
        vs = [bm.verts.new((x0 + k * 2 + x, y, 0.0)) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
        f = bm.faces.new(vs)
        a = math.radians(30 * k)
        for lp, (u, v) in zip(f.loops, ((0, 0), (0.2, 0), (0.2, 0.1), (0, 0.1))):
            lp[uv].uv = (0.1 + 0.4 * k + u * math.cos(a) - v * math.sin(a), 0.1 + 0.3 * k + u * math.sin(a) + v * math.cos(a))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def _uvs(ob):
    return [tuple(round(c, 6) for c in d.uv) for d in ob.data.uv_layers.active.data]


def _setup():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    a, b = _two_shells("picked", 0.0), _two_shells("other", 6.0)
    for ob in (a, b):
        ob.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    for o in (a, b):
        m = bmesh.from_edit_mesh(o.data)
        for seq in (m.verts, m.edges, m.faces):
            for el in seq:
                el.select = o is a
        bmesh.update_edit_mesh(o.data)
    return a, b


def test_shell_commands_leave_a_mesh_with_nothing_picked_alone():
    for op in OPS:
        a, b = _setup()
        bpy.ops.object.mode_set(mode='OBJECT')
        before_a, before_b = _uvs(a), _uvs(b)
        bpy.ops.object.mode_set(mode='EDIT')
        result = getattr(bpy.ops.allset, op)()
        bpy.ops.object.mode_set(mode='OBJECT')
        assert _uvs(b) == before_b, (op, "the mesh with nothing picked changed")
        if op not in ("uv_stack_similar",):     # the two shells differ in shape: nothing similar to stack
            assert result == {'FINISHED'} and _uvs(a) != before_a, (op, result, "the picked mesh didn't change")


def test_nothing_picked_anywhere_uses_every_shell():
    a, b = _setup()
    for o in (a, b):
        m = bmesh.from_edit_mesh(o.data)
        for f in m.faces:
            f.select = False
        for v in m.verts:
            v.select = False
        bmesh.update_edit_mesh(o.data)
    bpy.ops.object.mode_set(mode='OBJECT')
    before_a, before_b = _uvs(a), _uvs(b)
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.ops.allset.uv_orient_shells() == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    assert _uvs(a) != before_a and _uvs(b) != before_b
