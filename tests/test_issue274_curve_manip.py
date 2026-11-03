"""Issue #274 follow-up: curves and NURBS surfaces in edit mode (Maya component mode) get the kit's Maya
manipulator with the Move and Scale tools, like objects, mesh components and lattice points. It sits at the selected
control points (Bezier keys and handles by their own selection, NURBS CVs) and hides when nothing is selected."""

from importlib import import_module

import bpy

import kit

manipulator = import_module(kit.MODULE + ".ui.manipulator")


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _edit(ob):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')


def _center():
    bpy.context.scene.tool_settings.transform_pivot_point = 'MEDIAN_POINT'
    return manipulator.pivot_frame(bpy.context, 'TRANSLATE')[0]


def test_curve_and_surface_tools_use_the_maya_manipulator():
    for mode in ('EDIT_CURVE', 'EDIT_SURFACE'):
        assert mode in manipulator.MODES
        for idname in ("builtin.move", "builtin.scale"):
            item = manipulator._find_item(mode, idname)
            assert item is not None, (mode, idname)
            assert item.widget == manipulator.GROUP, (mode, idname, item.widget)


def test_bezier_keys_and_handles():
    _fresh()
    bpy.ops.curve.primitive_bezier_curve_add(location=(2.0, 0.0, 1.0))
    ob = bpy.context.active_object
    _edit(ob)
    assert bpy.context.mode == 'EDIT_CURVE'
    bp = ob.data.splines[0].bezier_points
    for p in bp:
        p.select_control_point = p.select_left_handle = p.select_right_handle = False
    assert not manipulator._has_selection(bpy.context)
    assert _center() is None
    bp[0].select_control_point = True
    bp[1].select_right_handle = True
    assert manipulator._has_selection(bpy.context)
    want = ob.matrix_world @ ((bp[0].co + bp[1].handle_right) / 2)
    assert (_center() - want).length < 1e-5, (_center(), want)


def test_nurbs_surface_cvs():
    _fresh()
    bpy.ops.surface.primitive_nurbs_surface_surface_add(location=(0.0, 3.0, 0.0))
    ob = bpy.context.active_object
    _edit(ob)
    assert bpy.context.mode == 'EDIT_SURFACE'
    pts = ob.data.splines[0].points
    for i, p in enumerate(pts):
        p.select = i in (0, 5)
    want = ob.matrix_world @ ((pts[0].co.xyz + pts[5].co.xyz) / 2)
    assert (_center() - want).length < 1e-5, (_center(), want)
    for p in pts:
        p.select = False
    assert not manipulator._has_selection(bpy.context)
    _fresh()
