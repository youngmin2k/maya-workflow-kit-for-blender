"""UV checker and texel density in the UV Editor: the checker toggle, checker density (Ctrl+Up / Ctrl+Down: whole
steps, at least 1) and texel density Get / Set on shells picked with UV Sync Selection off."""
from importlib import import_module

import bmesh
import bpy

import kit

mi = import_module(kit.MODULE + ".operators.menu_items")


def _plane(name="checker", size=1.0, uv_size=1.0, x0=0.0):
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("map1")
    vs = [bm.verts.new((x0 + x * size, y * size, 0.0)) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    f = bm.faces.new(vs)
    for lp, (u, v) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uv].uv = (u * uv_size, v * uv_size)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def _clear():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for m in list(bpy.data.materials):
        if m.get(mi.CHECKER_MAT):
            bpy.data.materials.remove(m)


def _scale(mat):
    node = mat.node_tree.nodes.get(mi.DENSITY_NODE)
    assert node is not None
    tex = next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE')
    assert tex.inputs["Vector"].links and tex.inputs["Vector"].links[0].from_node == node
    return tuple(round(x, 6) for x in node.inputs["Scale"].default_value)


def test_checker_density_steps():
    _clear()
    ob = _plane()
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    assert bpy.ops.allset.checker_toggle() == {'FINISHED'}
    mat = ob.material_slots[0].material
    assert mat.get(mi.CHECKER_MAT) and mi.checker_density(mat) == 1 and _scale(mat) == (1, 1, 1)
    for want in (2, 3, 4):
        assert bpy.ops.allset.checker_density(step=1) == {'FINISHED'}
        assert mi.checker_density(mat) == want and _scale(mat) == (want, want, 1), _scale(mat)
    for want in (3, 2, 1, 1, 1):         # never below 1
        assert bpy.ops.allset.checker_density(step=-1) == {'FINISHED'}
        assert mi.checker_density(mat) == want and _scale(mat) == (want, want, 1)
    bpy.ops.allset.checker_density(step=1)
    # the density stays with the checker through off / on
    assert bpy.ops.allset.checker_toggle() == {'FINISHED'} and not mi.checker_on(bpy.context)
    assert bpy.ops.allset.checker_toggle() == {'FINISHED'} and mi.checker_on(bpy.context)
    assert mi.checker_density(ob.material_slots[0].material) == 2
    bpy.ops.allset.checker_toggle()


def test_checker_material_from_an_older_file_gets_the_density_node():
    _clear()
    mat = mi._checker_material()
    tree = mat.node_tree
    for n in [n for n in tree.nodes if n.type in ('MAPPING', 'TEX_COORD')]:
        tree.nodes.remove(n)
    assert tree.nodes.get(mi.DENSITY_NODE) is None
    assert mi.set_checker_density(3) == 3
    assert _scale(mat) == (3, 3, 1)


def test_checker_density_keys():
    km = kit.maya_kc().keymaps["UV Editor"]
    got = {(k.type, k.ctrl, k.shift, k.alt): k.properties.step for k in km.keymap_items
           if k.idname == "allset.checker_density" and k.active}
    assert got == {('UP_ARROW', True, False, False): 1, ('DOWN_ARROW', True, False, False): -1}, got


def test_texel_density_set_on_uv_shells_with_sync_off():
    """Two planes of the same size, one with a 4 x larger UV square: Get on the small one, Set on the big one
    (its UVs picked with UV Sync Selection off) gives both the same density."""
    _clear()
    a = _plane("small", uv_size=0.25)
    b = _plane("big", uv_size=1.0, x0=3.0)
    for ob in (a, b):
        ob.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.mode_set(mode='EDIT')
    s = bpy.context.scene.allset_uv
    assert bpy.ops.allset.uv_component(mode='UV') == {'FINISHED'}
    assert not bpy.context.scene.tool_settings.use_uv_select_sync

    def pick(ob):
        """Only ``ob``'s face shown in the UV Editor (mesh selection), all its UVs selected."""
        for o in (a, b):
            bm = bmesh.from_edit_mesh(o.data)
            for seq in (bm.verts, bm.edges, bm.faces):
                for el in seq:
                    el.select = o is ob
            bmesh.update_edit_mesh(o.data)
        bpy.ops.uv.select_all(action='SELECT')

    pick(a)
    assert bpy.ops.allset.uv_texel_get() == {'FINISHED'}
    small = s.texel_density
    assert abs(small - 0.25 * s.map_size / (1.0 / units_maya())) < 1e-3 * small, small
    pick(b)
    assert bpy.ops.allset.uv_texel_set() == {'FINISHED'}
    assert bpy.ops.allset.uv_texel_get() == {'FINISHED'}
    assert abs(s.texel_density - small) < 1e-3 * small, (s.texel_density, small)
    # the small plane was not touched
    pick(a)
    bpy.ops.allset.uv_texel_get()
    assert abs(s.texel_density - small) < 1e-3 * small
    bpy.ops.object.mode_set(mode='OBJECT')


def units_maya():
    return import_module(kit.MODULE + ".operators.units").maya_unit(bpy.context.scene)


def test_unfold_with_one_mesh_picked_leaves_the_other_alone():
    """Two meshes in edit mode, UVs picked only on one: Unfold works on that mesh's shells only."""
    _clear()
    a = _plane("small", uv_size=0.25)
    b = _plane("big", uv_size=1.0, x0=3.0)
    bm = bmesh.new()
    bm.from_mesh(b.data)
    uv = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    for lp in bm.faces[0].loops:          # a skewed UV square: Unfold would change it
        lp[uv].uv = (lp[uv].uv.x + 0.3 * lp[uv].uv.y, lp[uv].uv.y)
    bm.to_mesh(b.data)
    bm.free()
    before = [tuple(round(c, 6) for c in d.uv) for d in b.data.uv_layers.active.data]
    for ob in (a, b):
        ob.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.allset.uv_component(mode='UV')
    for o in (a, b):
        m = bmesh.from_edit_mesh(o.data)
        for seq in (m.verts, m.edges, m.faces):
            for el in seq:
                el.select = o is a
        bmesh.update_edit_mesh(o.data)
    bpy.ops.uv.select_all(action='SELECT')
    assert bpy.ops.allset.uv_unfold() == {'FINISHED'}
    bpy.ops.object.mode_set(mode='OBJECT')
    after = [tuple(round(c, 6) for c in d.uv) for d in b.data.uv_layers.active.data]
    assert after == before, (before, after)
