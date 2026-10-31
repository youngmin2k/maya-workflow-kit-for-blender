"""Issue #274: a lattice in edit mode (Maya component mode).

* The Move and Scale tools of lattice edit mode use the kit's Maya manipulator, like object and mesh edit mode; it
  sits at the selected points and hides when no point is selected.
* S keys the selected lattice points' X / Y / Z, also on a lattice that a Bend deformer bends.
"""

from importlib import import_module

import bpy
from mathutils import Vector

import kit

manipulator = import_module(kit.MODULE + ".ui.manipulator")
compat = import_module(kit.MODULE + ".compat")


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.context.scene.frame_set(1)


def _only(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def _lattice(bend=False):
    _fresh()
    bpy.ops.object.add(type='LATTICE', location=(1.0, 2.0, 0.0))
    ob = bpy.context.active_object
    ob.data.points_w = 4
    if bend:
        _only(ob)
        assert bpy.ops.allset.deformer(kind='BEND') == {'FINISHED'}
        md = ob.modifiers[-1]
        assert md.type == 'SIMPLE_DEFORM'
        md.angle = 1.5
    _only(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    assert bpy.context.mode == 'EDIT_LATTICE'
    return ob


def test_lattice_move_and_scale_tools_use_the_maya_manipulator():
    assert 'EDIT_LATTICE' in manipulator.MODES
    for idname in ("builtin.move", "builtin.scale"):
        item = manipulator._find_item('EDIT_LATTICE', idname)
        assert item is not None, idname
        assert item.widget == manipulator.GROUP, (idname, item.widget)


def test_manipulator_sits_at_the_selected_points():
    ob = _lattice()
    pts = ob.data.points
    for i, p in enumerate(pts):
        p.select = i in (0, 1)
    assert manipulator._has_selection(bpy.context)
    want = ob.matrix_world @ ((pts[0].co_deform + pts[1].co_deform) / 2)
    bpy.context.scene.tool_settings.transform_pivot_point = 'MEDIAN_POINT'
    center, _frame, _otype = manipulator.pivot_frame(bpy.context, 'TRANSLATE')
    assert (center - want).length < 1e-5, (center, want)
    for p in pts:
        p.select = False
    assert not manipulator._has_selection(bpy.context)
    center, _frame, _otype = manipulator.pivot_frame(bpy.context, 'TRANSLATE')
    assert center is None


def _curves(idd):
    return sorted((fc.data_path, fc.array_index) for fc in compat.id_fcurves(idd))


def test_s_keys_points_of_a_bent_lattice():
    ob = _lattice(bend=True)
    for i, p in enumerate(ob.data.points):
        p.select = i == 5
    assert bpy.ops.allset.set_key('EXEC_DEFAULT', True) == {'FINISHED'}
    assert _curves(ob.data) == [("points[5].co_deform", a) for a in range(3)]
    co0 = Vector(ob.data.points[5].co_deform)
    bpy.context.scene.frame_set(10)
    ob.data.points[5].co_deform.x += 0.5
    assert bpy.ops.allset.set_key('EXEC_DEFAULT', True) == {'FINISHED'}
    bpy.context.scene.frame_set(1)
    assert (Vector(ob.data.points[5].co_deform) - co0).length < 1e-5
