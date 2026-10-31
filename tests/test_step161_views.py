"""G3 / G4 headless parts: Maya's hierarchy highlight in the selection wire, the
four view's Maya ortho cameras."""

from importlib import import_module

import bpy

import kit

wire = import_module(kit.MODULE + ".ui.selection_wire")
view = import_module(kit.MODULE + ".operators.view")


def _cube(name, parent=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1), (1, 2)], [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    return ob


def test_hierarchy_highlight_takes_the_nearest_selected_ancestor_colour():
    # Maya: group1 selected -> its pCube1 white,
    # pCube2 (lead) -> its pCube3 green
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    group1 = bpy.data.objects.new("group1", None)
    bpy.context.scene.collection.objects.link(group1)
    c1 = _cube("pCube1", group1)
    c2 = _cube("pCube2")
    c3 = _cube("pCube3", c2)
    c4 = _cube("pCube4", c3)
    for o in bpy.context.scene.objects:
        o.select_set(o in (group1, c2, c4))
    bpy.context.view_layer.objects.active = c2
    got = {ob.name: lead for ob, lead in wire.highlighted(bpy.context)}
    assert got == {"pCube1": False, "pCube2": True, "pCube3": True, "pCube4": False}, got
    c1.hide_set(True)
    assert "pCube1" not in {ob.name for ob, _l in wire.highlighted(bpy.context)}


class _RV3D:
    def __init__(self, persp, quat):
        from mathutils import Quaternion
        self.view_perspective = persp
        self.view_rotation = Quaternion(quat)


def test_ortho_keys_and_maya_width():
    import math
    from mathutils import Euler
    top = _RV3D('ORTHO', (1, 0, 0, 0))
    front = _RV3D('ORTHO', Euler((math.pi / 2, 0, 0)).to_quaternion())
    assert view.ortho_key(top) == "TOP"
    assert view.ortho_key(front).startswith("FRONT")
    assert view.ortho_key(_RV3D('PERSP', (1, 0, 0, 0))) is None

    class Space:
        lens = 70.0
    u = import_module(kit.MODULE + ".operators.units").maya_unit(bpy.context.scene)
    # width along the longer side = distance x 72 / lens (gui_step161_views) = 30 Maya units
    assert abs(view.maya_ortho_distance(Space()) * 72 / 70 - 30 * u) < 1e-9
