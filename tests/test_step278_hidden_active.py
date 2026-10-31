"""#187: commands that switch a hidden active object into Edit / Pose mode warn the kit's way
("<name> is hidden: show it (Display > Show) first") instead of Blender's "Cannot edit hidden object" or a Python
error, and leave the scene as it was. Component modes (F9 / F10 / F11 / F7): tests/test_issue187_hidden_components.py.
"""

from importlib import import_module

import bpy

import kit

errors = import_module(kit.MODULE + ".operators.maya_errors")


def _scene(kind='MESH', hide="viewport"):
    if bpy.context.object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    if kind == 'MESH':
        bpy.ops.mesh.primitive_cube_add()
    elif kind == 'ARMATURE':
        bpy.ops.object.armature_add()
    else:
        bpy.ops.curve.primitive_bezier_curve_add()
    ob = bpy.context.active_object
    if hide == "viewport":
        ob.hide_viewport = True
    else:
        ob.hide_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.context.view_layer.update()
    assert not ob.visible_get()
    return ob


class _Op:
    def __init__(self):
        self.reports = []

    def report(self, kind, text):
        self.reports.append((set(kind), text))


def test_blender_message_becomes_the_kit_warning():
    ob = _scene()
    op = _Op()
    errors.report_nested(op, RuntimeError("Error: Cannot edit hidden object"))
    assert op.reports == [({'WARNING'}, f"{ob.name} is hidden: show it (Display > Show) first")], op.reports
    op = _Op()
    errors.report_nested(op, RuntimeError("Error: Something else"))            # other Errors stay Errors
    assert op.reports == [({'ERROR'}, "Something else")]


def test_refuse_hidden():
    ob = _scene()
    op = _Op()
    assert errors.refuse_hidden(op, ob) and "is hidden" in op.reports[0][1]
    assert not errors.refuse_hidden(_Op(), None)
    ob.hide_viewport = False
    bpy.context.view_layer.update()
    assert not errors.refuse_hidden(_Op(), ob)


def _call(op, **kw):
    try:
        return op('EXEC_DEFAULT', **kw)
    except RuntimeError as ex:
        return str(ex)


def test_f8_on_a_hidden_mesh_and_skeleton():
    for kind in ('MESH', 'ARMATURE'):
        for hide in ("viewport", "eye"):
            ob = _scene(kind, hide)
            res = _call(bpy.ops.allset.toggle_sel_mode)
            assert res == {'CANCELLED'}, (kind, hide, res)
            assert bpy.context.mode == 'OBJECT' and not ob.visible_get()


def test_component_marking_menu_cv_and_mesh():
    for kind, typ in (('CURVE', 'CV'), ('MESH', 'VERT')):
        ob = _scene(kind)
        res = _call(bpy.ops.allset.mm_component, type=typ)
        assert res == {'CANCELLED'}, (kind, res)
        assert bpy.context.mode == 'OBJECT' and bpy.context.view_layer.objects.active == ob


def test_status_line_selection_mode():
    ob = _scene()
    res = _call(bpy.ops.allset.select_mode, mode="COMPONENT")
    assert res == {'CANCELLED'}, res
    assert bpy.context.mode == 'OBJECT' and not ob.visible_get()


def test_tool_box_armature_mode():
    _scene('ARMATURE')
    res = _call(bpy.ops.allset.armature_mode, mode='POSE')
    assert res == {'CANCELLED'}, res
    assert bpy.context.mode == 'OBJECT'


def test_quad_draw_on_a_hidden_mesh():
    # a hidden mesh is never the selected one: Quad Draw starts a new mesh and leaves the hidden one alone
    ob = _scene()
    before = len(ob.data.vertices)
    res = _call(bpy.ops.allset.quad_draw_start)
    assert res == {'FINISHED'}, res
    assert not ob.visible_get() and len(ob.data.vertices) == before
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def test_cut_and_sew_and_append_on_a_hidden_mesh():
    for idname in ("cut_sew_tool_set", "append_polygon_start"):
        op = getattr(bpy.ops.allset, idname, None)
        if op is None:
            continue
        ob = _scene()
        res = _call(op)
        assert res in ({'CANCELLED'},) or "poll" in str(res), (idname, res)
        assert "Cannot edit hidden" not in str(res), (idname, res)
        assert bpy.context.mode == 'OBJECT' and not ob.visible_get()


def test_visible_objects_still_switch():
    ob = _scene()
    ob.hide_viewport = False
    bpy.context.view_layer.update()
    assert _call(bpy.ops.allset.toggle_sel_mode) == {'FINISHED'}
    assert bpy.context.mode == 'EDIT_MESH'
    bpy.ops.object.mode_set(mode='OBJECT')
