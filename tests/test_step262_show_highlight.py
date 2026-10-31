"""Issue #173: the panel Show menu's Selection Highlighting and NURBS Curves rows really drive what the
viewport draws — icon == setting == behaviour — for the kit selection wire and for rig controls drawn as bone
custom shapes. The drawn pixels: tests/gui/gui_step262_show.py.
"""

from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

wire = import_module(kit.MODULE + ".ui.selection_wire")
cc = import_module(kit.MODULE + ".ui.curve_controls")
pm = import_module(kit.MODULE + ".ui.panel_menus")
pmd = import_module(kit.MODULE + ".ui.panel_menu_data")
compat = import_module(kit.MODULE + ".compat")


def _clear():
    if bpy.context.object is not None and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _rig():
    """Armature `rig` (bones ctrl = curve custom shape, body = plain) with a child mesh `body_geo`, and a hidden
    circle `ctrl_shape` (Blender's usual control rig layout)."""
    _clear()
    sc = bpy.context.scene
    circle = bpy.data.curves.new("ctrl_shape", 'CURVE')
    sp = circle.splines.new('POLY')
    sp.points.add(3)
    shape = bpy.data.objects.new("ctrl_shape", circle)
    sc.collection.objects.link(shape)
    shape.hide_set(True)
    arm = bpy.data.armatures.new("rig")
    rig = bpy.data.objects.new("rig", arm)
    sc.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for name, z in (("ctrl", 0.0), ("body", 1.0)):
        eb = arm.edit_bones.new(name)
        eb.head, eb.tail = (0, 0, z), (0, 0, z + 1)
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.pose.bones["ctrl"].custom_shape = shape
    me = bpy.data.meshes.new("body_geo")
    me.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1), (1, 2)], [])
    body = bpy.data.objects.new("body_geo", me)
    sc.collection.objects.link(body)
    body.parent = rig
    return rig, body


class _Screen(dict):
    """Stand-in screen (ID-property dict + areas) for -b, where there is no window."""
    def __init__(self, space):
        super().__init__()
        self.areas = [SimpleNamespace(spaces=SimpleNamespace(active=SimpleNamespace())),
                      SimpleNamespace(spaces=SimpleNamespace(active=space))]


def _ctx(outline=False):
    """bpy.context with a stand-in 3D View (no real view in -b); a Maya Workflow Kit view has Blender's outline off."""
    space = SimpleNamespace(type='VIEW_3D', overlay=SimpleNamespace(show_outline_selected=outline),
                            shading=None)
    c = bpy.context
    return SimpleNamespace(space_data=space, screen=_Screen(space), view_layer=c.view_layer,
                           selected_objects=c.selected_objects, scene=c.scene)


def test_selection_highlighting_off_draws_no_wire():
    rig, body = _rig()
    for o in bpy.context.scene.objects:
        o.select_set(o is body)
    bpy.context.view_layer.objects.active = body
    ctx = _ctx()
    # Maya Workflow Kit view: Blender's outline off, the row checked, the kit wire drawn
    assert pm.state(ctx, "SELECTION_HILITE") is True
    assert [o.name for o, _l in wire.highlighted(ctx)] == ["body_geo"]
    pm.apply(ctx, "SELECTION_HILITE")
    assert pm.state(ctx, "SELECTION_HILITE") is False and wire.highlighted(ctx) == []
    assert wire.HILITE_OFF in ctx.screen                     # kept on the screen (saved with the file)
    pm.apply(ctx, "SELECTION_HILITE")
    assert pm.state(ctx, "SELECTION_HILITE") is True and wire.HILITE_OFF not in ctx.screen
    assert ctx.space_data.overlay.show_outline_selected is False     # stays off in a Maya view
    # a Blender view with the outline on: off hides it too, on brings it back
    ctx = _ctx(outline=True)
    pm.apply(ctx, "SELECTION_HILITE")
    assert ctx.space_data.overlay.show_outline_selected is False and wire.highlighted(ctx) == []
    pm.apply(ctx, "SELECTION_HILITE")
    assert ctx.space_data.overlay.show_outline_selected is True
    assert ("set", "SELECTION_HILITE", "Selection Highlighting") in pmd.SHOW


def test_pose_mode_control_pick_doesnt_highlight_the_child_mesh():
    rig, body = _rig()
    for o in bpy.context.scene.objects:
        o.select_set(o is rig)
    bpy.context.view_layer.objects.active = rig
    # object mode: the armature's hierarchy is selected (Maya hierarchy highlight)
    assert "body_geo" in [o.name for o, _l in wire.highlighted(bpy.context)]
    bpy.ops.object.mode_set(mode='POSE')
    try:
        assert rig.select_get() and rig.mode == 'POSE'
        assert wire.highlighted(bpy.context) == [], wire.highlighted(bpy.context)
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')


def test_nurbs_curves_hides_curve_shaped_bone_controls_and_back():
    rig, _body = _rig()
    ctrl, plain = rig.pose.bones["ctrl"], rig.pose.bones["body"]
    sc = bpy.context.scene
    assert cc.controls(sc) == [ctrl]
    cc.show(sc, False)
    assert compat.bone_hidden(ctrl) and not compat.bone_hidden(plain) and ctrl.get(cc.MARK)
    cc.show(sc, True)
    assert not compat.bone_hidden(ctrl) and cc.MARK not in ctrl
    # a control the user hid stays hidden when NURBS Curves comes back
    compat.set_bone_hidden(ctrl, True)
    cc.show(sc, False)
    assert cc.MARK not in ctrl
    cc.show(sc, True)
    assert compat.bone_hidden(ctrl)
    compat.set_bone_hidden(ctrl, False)
    # disable gives back what the kit hid
    cc.show(sc, False)
    cc.release_all()
    assert not compat.bone_hidden(ctrl) and cc.MARK not in ctrl


def test_show_menu_row_icon_equals_view_flag_equals_controls():
    rig, _body = _rig()
    ctrl = rig.pose.bones["ctrl"]
    assert ("set", "SHOW_NURBS_CURVES", "NURBS Curves") in pmd.SHOW
    space = SimpleNamespace(type='VIEW_3D', show_object_viewport_curve=True, shading=None, overlay=None)
    ctx = SimpleNamespace(space_data=space, scene=bpy.context.scene)
    assert pm.state(ctx, "SHOW_NURBS_CURVES") is True
    pm.apply(ctx, "SHOW_NURBS_CURVES")
    assert space.show_object_viewport_curve is False and pm.state(ctx, "SHOW_NURBS_CURVES") is False
    assert compat.bone_hidden(ctrl)
    pm.apply(ctx, "SHOW_NURBS_CURVES")
    assert space.show_object_viewport_curve is True and not compat.bone_hidden(ctrl)


def test_hidden_controls_survive_save_and_open():
    import os
    import tempfile
    rig, _body = _rig()
    cc.show(bpy.context.scene, False)
    path = os.path.join(tempfile.mkdtemp(prefix="allset262_"), "rig.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    bpy.ops.wm.open_mainfile(filepath=path)
    ctrl = bpy.data.objects["rig"].pose.bones["ctrl"]
    assert compat.bone_hidden(ctrl) and ctrl.get(cc.MARK)
    cc.show(bpy.context.scene, True)       # NURBS Curves back on after reopening: the mark brings it back
    assert not compat.bone_hidden(ctrl)
