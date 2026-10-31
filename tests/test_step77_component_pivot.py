"""Step 77: edit-mode Insert = the D component pivot edit as a toggle; a turned 3D cursor becomes the
"Maya Pivot" Move orientation. GUI: tests/gui/gui_step77_component_pivot.py."""

from importlib import import_module

import bpy
from mathutils import Euler, Matrix

import kit

hold = import_module(kit.MODULE + ".operators.hold")
pivot = import_module(kit.MODULE + ".operators.pivot")


def _kmis(km, key):
    kc = kit.maya_kc()
    return [k for k in kc.keymaps[km].keymap_items if k.active and k.type == key and k.value == 'PRESS'
            and not (k.shift or k.ctrl or k.alt)]


def _edit_cube():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.mesh.primitive_cube_add()
    bpy.ops.object.mode_set(mode='EDIT')
    sc = bpy.context.scene
    sc.cursor.location = (0, 0, 0)
    sc.cursor.rotation_mode = 'XYZ'
    sc.cursor.rotation_euler = (0, 0, 0)
    sc.tool_settings.transform_pivot_point = 'BOUNDING_BOX_CENTER'
    sc.transform_orientation_slots[pivot.MOVE_SLOT].type = 'GLOBAL'
    return sc


def _cursor_orientation():
    tool = bpy.context.workspace.tools.from_space_view3d_mode('EDIT_MESH', create=True)
    return tool.operator_properties(hold.CURSOR_OP).orientation


def test_insert_is_bound_in_mesh_and_object_mode():
    assert [k.idname for k in _kmis("Mesh", "INSERT")] == ["allset.pivot_toggle"]
    assert [k.idname for k in _kmis("Object Mode", "INSERT")] == ["allset.pivot_toggle"]
    assert _kmis("Mesh", "D")[0].properties.name == "component_pivot"


def test_tap_clears_to_mayas_component_manipulator():
    after = hold.component_pivot_after
    assert after('CURSOR', False) == 'BOUNDING_BOX_CENTER'
    assert after('MEDIAN_POINT', False) == 'MEDIAN_POINT'
    assert after('BOUNDING_BOX_CENTER', True) == 'CURSOR'


def test_turned():
    a = Matrix.Identity(3)
    assert not hold.turned(a, a.copy())
    assert hold.turned(a, Euler((0, 0, 0.3)).to_matrix())


def test_insert_toggles_the_cursor_pivot_edit():
    sc = _edit_cube()
    before = _cursor_orientation()
    assert bpy.ops.allset.pivot_toggle() == {'FINISHED'}
    assert hold.COMPONENT.on and hold.COMPONENT.toggled
    assert sc.tool_settings.transform_pivot_point == 'CURSOR'
    assert _cursor_orientation() == 'GEOM', "Maya snapPivotOri: component click orients the pivot"
    assert not sc.tool_settings.use_transform_data_origin, "edit mode doesn't use Affect Only Origins"
    sc.cursor.location = (0.5, 0.0, 1.0)                      # the user placed the pivot
    bpy.ops.allset.pivot_toggle()
    assert not hold.COMPONENT.on
    assert sc.tool_settings.transform_pivot_point == 'CURSOR', "a placed pivot stays"
    assert _cursor_orientation() == before
    assert sc.transform_orientation_slots[pivot.MOVE_SLOT].type == 'GLOBAL', "not turned: axis kept"
    # tap on / off without moving: the custom pivot goes back to the bbox centre
    bpy.ops.allset.pivot_toggle()
    bpy.ops.allset.pivot_toggle()
    assert sc.tool_settings.transform_pivot_point == 'BOUNDING_BOX_CENTER'


def test_turned_cursor_becomes_maya_pivot_orientation():
    sc = _edit_cube()
    bpy.ops.allset.pivot_toggle()
    sc.cursor.location = (0.0, 0.0, 1.0)
    sc.cursor.rotation_euler = (0.4, 0.0, 0.0)                # cursor tool GEOM on a tilted face
    bpy.ops.allset.pivot_toggle()
    slot = sc.transform_orientation_slots[pivot.MOVE_SLOT]
    assert slot.type == pivot.ORIENT_NAME, slot.type
    want = Euler((0.4, 0.0, 0.0)).to_matrix()
    got = slot.custom_orientation.matrix
    assert not hold.turned(want, got), (want, got)


def test_leaving_edit_mode_closes_the_toggle():
    sc = _edit_cube()
    bpy.ops.allset.pivot_toggle()
    assert hold.COMPONENT.on
    bpy.ops.object.mode_set(mode='OBJECT')
    hold.COMPONENT.tick(bpy.context)
    assert not hold.COMPONENT.on
    assert sc.tool_settings.transform_pivot_point != 'CURSOR'
    assert hold.COMPONENT.pending_tool is not None, "the tool comes back in edit mode"
    bpy.ops.object.mode_set(mode='EDIT')
    hold.COMPONENT.tick(bpy.context)
    assert hold.COMPONENT.pending_tool is None


def test_object_mode_insert_unchanged():
    sc = _edit_cube()
    bpy.ops.object.mode_set(mode='OBJECT')
    ts = sc.tool_settings
    ts.use_transform_data_origin = False
    bpy.ops.allset.pivot_toggle()
    assert ts.use_transform_data_origin and not hold.COMPONENT.on
    bpy.ops.allset.pivot_toggle()
    assert not ts.use_transform_data_origin


def test_object_mode_drops_a_placed_component_pivot():
    """#263: a component pivot placed (and turned) in edit mode no longer drives the object manipulator after
    leaving edit mode — Center Pivot and Move work on the object pivot again."""
    sc = _edit_cube()
    ts = sc.tool_settings
    ts.transform_pivot_point = 'MEDIAN_POINT'
    bpy.ops.allset.pivot_toggle()
    sc.cursor.location = (0.5, 0.0, 1.0)
    sc.cursor.rotation_euler = (0.4, 0.0, 0.0)
    bpy.ops.allset.pivot_toggle()
    assert hold.COMPONENT.custom and ts.transform_pivot_point == 'CURSOR'
    assert sc.transform_orientation_slots[pivot.MOVE_SLOT].type == pivot.ORIENT_NAME
    bpy.ops.object.mode_set(mode='OBJECT')
    hold.COMPONENT.tick(bpy.context)
    assert not hold.COMPONENT.custom
    assert ts.transform_pivot_point == 'MEDIAN_POINT', ts.transform_pivot_point
    assert sc.transform_orientation_slots[pivot.MOVE_SLOT].type == 'GLOBAL', sc.transform_orientation_slots[pivot.MOVE_SLOT].type
    ob = bpy.context.active_object
    ob.location = (2.0, 0.0, 0.0)
    assert bpy.ops.allset.center_pivot() == {'FINISHED'}
    assert ts.transform_pivot_point != 'CURSOR'
