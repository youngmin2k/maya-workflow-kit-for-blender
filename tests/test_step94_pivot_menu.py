"""The pivot-edit RMB marking menu (D / Insert) — Maya positions, when it opens, check boxes, Reset
(objects and components), Pin Component Pivot, Exit."""

from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

marking = import_module(kit.MODULE + ".marking")
menus = import_module(kit.MODULE + ".marking.menus")
engine = import_module(kit.MODULE + ".marking.engine")
draw = import_module(kit.MODULE + ".marking.draw")
hold = import_module(kit.MODULE + ".operators.hold")
pivot_menu = import_module(kit.MODULE + ".operators.pivot_menu")
freeze = import_module(kit.MODULE + ".operators.freeze")


def _cube():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    me = bpy.data.meshes.new("pCubeShape1")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("pCube1", me)
    bpy.context.scene.collection.objects.link(ob)
    for o in bpy.context.scene.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    return ob


def test_menu_matches_maya():
    m = menus.PIVOT_EDIT
    assert {pos: label for pos, (label, _a) in m.radial.items()} == {
        "N": "Pin Component Pivot", "S": "Reset Pivot", "NW": "Snap Pivot Orientation", "NE": "Snap Pivot Position",
        "SW": "Reset Pivot Orientation", "SE": "Reset Pivot Position", "W": "Show Orientation Handle", "E": "Exit"}
    assert m.items[0] == ("Bake Pivot Orientation", ("item", "Modify/Bake Pivot"))
    assert menus.MENUS["PIVOT_EDIT"] is m


def test_resolve_only_while_editing_a_pivot():
    ob = _cube()
    ts = bpy.context.scene.tool_settings
    hold.set_pivot_mode(ts, False)
    assert marking.resolve("RMB", bpy.context, ob) != ("pie", marking.idname("PIVOT_EDIT"))
    hold.set_pivot_mode(ts, True)
    assert marking.resolve("RMB", bpy.context, ob) == ("pie", marking.idname("PIVOT_EDIT"))
    assert marking.resolve("RMB", bpy.context, None) == ("pie", marking.idname("PIVOT_EDIT"))
    hold.set_pivot_mode(ts, False)


def test_check_boxes_follow_the_options():
    for opt, _prop, default in pivot_menu.OPTIONS:
        action = ("allset.pivot_option", {"option": opt})
        assert engine.is_toggle(action)
        assert draw.checked(action) is default, (opt, default)        # defaults like Maya: pin off, snaps on
    assert bpy.ops.allset.pivot_option(option="PIN") == {'FINISHED'}
    assert draw.checked(("allset.pivot_option", {"option": "PIN"})) is True
    bpy.ops.allset.pivot_option(option="PIN")
    assert not engine.is_toggle(("allset.pivot_reset", {}))


def test_object_reset_pivot():
    ob = _cube()
    hold.set_pivot_mode(bpy.context.scene.tool_settings, True)
    freeze.shift_pivot(ob, Vector((1.0, 0.0, 0.0)))                    # a custom pivot 1 unit off
    assert Vector(ob.delta_location).length > 0.5
    bpy.context.view_layer.update()
    world = [ob.matrix_world @ v.co for v in ob.data.vertices]
    assert bpy.ops.allset.pivot_reset() == {'FINISHED'}
    bpy.context.view_layer.update()
    assert Vector(ob.delta_location).length < 1e-6
    assert all((ob.matrix_world @ v.co - w).length < 1e-5 for v, w in zip(ob.data.vertices, world)), "geometry stays"
    assert bpy.ops.allset.pivot_exit() == {'FINISHED'}
    assert not bpy.context.scene.tool_settings.use_transform_data_origin


def test_reset_position_mode_center_or_zero():
    """Center Position on Reset (default): the pivot goes to the bounding box centre; Zero: to the origin."""
    reset = ("allset.pivot_option", {"option": "RESET_CENTER"}), ("allset.pivot_option", {"option": "RESET_ZERO"})
    assert dict(e for e in menus.PIVOT_EDIT.items if e != menus.DIVIDER)["Center Position on Reset"] == reset[0]
    assert dict(e for e in menus.PIVOT_EDIT.items if e != menus.DIVIDER)["Zero Position on Reset"] == reset[1]
    assert draw.checked(reset[0]) is True and draw.checked(reset[1]) is False, "Center is the default"
    for mode, expect in (("RESET_CENTER", Vector((3.0, 0.0, 0.0))), ("RESET_ZERO", Vector((0.0, 0.0, 0.0)))):
        ob = _cube()
        for v in ob.data.vertices:                                      # geometry centred at x = 3
            v.co.x += 3.0
        freeze.shift_pivot(ob, Vector((1.0, 0.0, 0.0)))
        bpy.context.view_layer.update()
        world = [ob.matrix_world @ v.co for v in ob.data.vertices]
        assert bpy.ops.allset.pivot_option(option=mode) == {'FINISHED'}
        assert draw.checked(("allset.pivot_option", {"option": mode})) is True
        assert bpy.ops.allset.pivot_reset(orientation=False) == {'FINISHED'}
        bpy.context.view_layer.update()
        pivot = ob.matrix_world.translation
        assert (pivot - expect).length < 1e-5, (mode, tuple(pivot))
        assert all((ob.matrix_world @ v.co - w).length < 1e-5 for v, w in zip(ob.data.vertices, world))
    bpy.ops.allset.pivot_option(option="RESET_CENTER")


def _edit_select(ob, pred):
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        v.select = pred(v.co)
    bm.select_flush(True)
    bm.select_history.clear()
    sel = [v for v in bm.verts if v.select]
    if sel:
        bm.select_history.add(sel[0])
    bmesh.update_edit_mesh(ob.data)


def test_component_reset_and_pin():
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    ts, cursor = bpy.context.scene.tool_settings, bpy.context.scene.cursor
    _edit_select(ob, lambda co: co.z > 0)                              # the top face: centre (0, 0, 1)
    assert (hold.selection_center(bpy.context) - Vector((0, 0, 1))).length < 1e-6
    cursor.location = (5.0, 5.0, 5.0)
    cursor.rotation_euler = (0.3, 0.0, 0.0)
    hold.COMPONENT.start(bpy.context, toggled=True)
    cursor.location = (3.0, 0.0, 0.0)                                  # "placed" a custom pivot
    assert bpy.ops.allset.pivot_reset() == {'FINISHED'}
    assert (cursor.location - Vector((0, 0, 1))).length < 1e-6
    assert all(abs(a) < 1e-9 for a in cursor.rotation_euler)
    hold.COMPONENT.finish(bpy.context)
    assert ts.transform_pivot_point != 'CURSOR' and not hold.COMPONENT.custom, "after a reset there is no custom pivot"
    # a placed pivot, Pin off (default, like Maya): a new selection drops it
    hold.COMPONENT.start(bpy.context, toggled=True)
    cursor.location = (3.0, 0.0, 0.0)
    hold.COMPONENT.finish(bpy.context)
    assert ts.transform_pivot_point == 'CURSOR' and hold.COMPONENT.custom
    hold.COMPONENT.tick(bpy.context)
    assert ts.transform_pivot_point == 'CURSOR', "same selection: kept"
    _edit_select(ob, lambda co: co.x > 0)
    hold.COMPONENT.tick(bpy.context)
    assert ts.transform_pivot_point == 'BOUNDING_BOX_CENTER' and not hold.COMPONENT.custom
    # Pin on: kept across the change
    bpy.context.window_manager.allset_pin_pivot = True
    hold.COMPONENT.start(bpy.context, toggled=True)
    cursor.location = (2.0, 0.0, 0.0)
    hold.COMPONENT.finish(bpy.context)
    _edit_select(ob, lambda co: co.y > 0)
    hold.COMPONENT.tick(bpy.context)
    assert ts.transform_pivot_point == 'CURSOR', "pinned"
    bpy.context.window_manager.allset_pin_pivot = False
    bpy.ops.object.mode_set(mode='OBJECT')
    hold.COMPONENT.tick(bpy.context)
    assert not hold.COMPONENT.custom


def test_snap_options_drive_the_cursor_tool():
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    wm = bpy.context.window_manager
    bpy.ops.wm.tool_set_by_id(name=hold.CURSOR_TOOL, space_type='VIEW_3D')
    hold.apply_cursor_options(bpy.context)
    tool = bpy.context.workspace.tools.from_space_view3d_mode('EDIT_MESH', create=False)
    props = tool.operator_properties(hold.CURSOR_OP)
    assert props.orientation == 'GEOM' and props.use_depth
    wm.allset_snap_pivot_ori = False
    wm.allset_snap_pivot_pos = False
    hold.apply_cursor_options(bpy.context)
    assert props.orientation == 'NONE' and not props.use_depth
    wm.allset_snap_pivot_ori = wm.allset_snap_pivot_pos = True
    bpy.ops.object.mode_set(mode='OBJECT')
    del ob
