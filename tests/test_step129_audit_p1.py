"""Maya menu items and keys in component mode (#39, #17, #18; Maya 2022),
Paint Skin Weights normalization (#20) and the switch to Blender in the Maya
Workflow Kit template file (#19). GUI: tests/gui/gui_step129_*.py."""

from importlib import import_module

import bmesh
import bpy
from mathutils import Vector

import kit

menu_map = import_module(kit.MODULE + ".ui.menu_map")


def _mod(name):
    return import_module(f"{kit.MODULE}.{name}")


# --- #39 / #17 / #18: component mode ----------------------------------------------------------------------------

def _edit_one_face(location_x=0.0):
    """pCube1 in face mode with face 0 selected (Maya: F11, click one face)."""
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    ob.location.x = location_x
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_mode(type='FACE')
    bpy.ops.mesh.select_all(action='DESELECT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    bm.faces[0].select_set(True)
    bmesh.update_edit_mesh(ob.data)
    return ob


def _selected_faces(ob):
    return sorted(f.index for f in bmesh.from_edit_mesh(ob.data).faces if f.select)


def _faces(ob):
    return len(bmesh.from_edit_mesh(ob.data).faces) if ob.mode == 'EDIT' else len(ob.data.polygons)


def _item(path):
    return bpy.ops.allset.menu_item(item=path)


def test_component_select_items_act_on_components():
    # Maya SelectAll / InvertSelection keep component mode and act on the faces; SelectNone clears and goes back
    # to object mode.
    ob = _edit_one_face()
    assert _item("Select/All") == {'FINISHED'}
    assert bpy.context.mode == 'EDIT_MESH' and len(_selected_faces(ob)) == 6
    ob = _edit_one_face()
    assert _item("Select/Inverse") == {'FINISHED'}
    assert _selected_faces(ob) == [1, 2, 3, 4, 5]
    ob = _edit_one_face()
    assert _item("Select/Deselect All") == {'FINISHED'}
    assert bpy.context.mode == 'OBJECT' and not bpy.context.selected_objects
    assert not any(p.select for p in ob.data.polygons)


def test_component_edit_delete_deletes_faces():
    ob = _edit_one_face()
    assert _item("Edit/Delete") == {'FINISHED'}
    assert bpy.context.mode == 'EDIT_MESH' and _faces(ob) == 5
    ob = _edit_one_face()
    assert _item("Edit/Cut") == {'FINISHED'}         # Maya Cut on faces deletes them (Maya warns)
    assert _faces(ob) == 5


def test_component_group_makes_an_empty_group():
    # Maya: Edit > Group with only faces selected makes an empty group null1 and selects it; pCube1 stays put
    ob = _edit_one_face()
    before = set(bpy.data.objects)
    assert _item("Edit/Group") == {'FINISHED'}
    new = [o for o in bpy.data.objects if o not in before]
    assert len(new) == 1 and new[0].name.startswith("null") and new[0].type == 'EMPTY', new
    assert ob.parent is None
    assert bpy.context.mode == 'OBJECT' and bpy.context.active_object == new[0]


def test_component_object_commands_follow_maya():
    # Freeze / Reset / Delete History / Select Hierarchy: Maya runs them with no effect in component mode
    for path in ("Modify/Freeze Transformations", "Modify/Reset Transformations", "Select/Hierarchy",
                 "Edit/Delete by Type/History"):
        ob = _edit_one_face(location_x=2.0)
        assert _item(path) == {'CANCELLED'}, path
        assert bpy.context.mode == 'EDIT_MESH' and abs(ob.location.x - 2.0) < 1e-9 and _selected_faces(ob) == [0], \
            path
    # Duplicate / Duplicate Special: "No object(s) to duplicate"; Parent / Unparent: "Cannot parent components"
    for path in ("Edit/Duplicate", "Edit/Duplicate Special", "Edit/Parent", "Edit/Unparent"):
        ob = _edit_one_face()
        n = len(bpy.data.objects)
        assert _item(path) == {'CANCELLED'}, path
        assert len(bpy.data.objects) == n and _faces(ob) == 6 and bpy.context.mode == 'EDIT_MESH', path
    # Duplicate with Transform duplicates the object; Maya stays in component mode on pCube1's face
    ob = _edit_one_face()
    n = len(bpy.data.objects)
    assert _item("Edit/Duplicate with Transform") == {'FINISHED'}
    assert len(bpy.data.objects) == n + 1
    assert bpy.context.mode == 'EDIT_MESH' and bpy.context.edit_object == ob and _selected_faces(ob) == [0]
    assert list(bpy.context.objects_in_mode) == [ob]


def test_component_rules_name_real_items():
    for path in menu_map.EDIT_MODE:
        assert path in menu_map.MAP, path


def test_mesh_ctrl_d_is_maya_duplicate():
    # #17: Blender's mesh.duplicate_move copied faces inside the mesh; Maya's Duplicate in component mode
    # duplicates nothing ("No object(s) to duplicate")
    km = kit.maya_kc().keymaps["Mesh"]
    items = [k for k in km.keymap_items if k.active and k.type == 'D' and k.value == 'PRESS' and k.ctrl
             and not (k.shift or k.alt or k.oskey)]
    assert [k.idname for k in items] == ["allset.component_command"], [k.idname for k in items]
    assert items[0].properties.item == "Edit/Duplicate"
    ob = _edit_one_face()
    n = len(bpy.data.objects)
    assert bpy.ops.allset.component_command(item="Edit/Duplicate") == {'CANCELLED'}
    assert len(bpy.data.objects) == n and _faces(ob) == 6


# --- #20: Paint Skin Weights normalizes (Maya Interactive) -------------------------------------------------------

def _bound_cylinder():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)
    joints = _mod("operators.joints")
    arm = joints.new_skeleton(bpy.context)
    parent = None
    for p in ((0, 0, 0), (0, 0, 1), (0, 0, 2)):
        parent = joints.add_joint(arm, Vector(p), parent, length=0.5)
    joints.finish(bpy.context, arm, ["joint1", "joint2", "joint3"])
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=2.6, location=(0, 0, 1.3), vertices=12)
    cyl = bpy.context.active_object
    with bpy.context.temp_override(object=cyl, active_object=cyl):
        cyl.modifiers.new("sub", 'SUBSURF').levels = 2
        bpy.ops.object.modifier_apply(modifier="sub")
    arm.select_set(True)
    cyl.select_set(True)
    bpy.context.view_layer.objects.active = cyl
    bpy.ops.allset.bind_skin()
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    cyl.select_set(True)
    bpy.context.view_layer.objects.active = cyl
    return arm, cyl


def _sums(ob):
    return [sum(g.weight for g in v.groups) for v in ob.data.vertices]


def test_paint_skin_weights_normalizes_interactively():
    _arm, cyl = _bound_cylinder()
    ts = bpy.context.scene.tool_settings
    ts.use_auto_normalize = False                           # Blender's factory value
    assert bpy.ops.allset.paint_skin_weights() == {'FINISHED'}
    assert ts.use_auto_normalize, "Maya Paint Skin Weights normalizes interactively (skinCluster normalizeWeights 1)"
    cyl.vertex_groups.active_index = cyl.vertex_groups["joint3"].index
    paint_weights = _mod("ui.paint_weights")
    _mod("compat").unified_paint_settings(ts).weight = 1.0
    ts.weight_paint.brush.weight = 1.0
    ts.weight_paint.brush.blend = 'MIX'
    mod, name = paint_weights.FLOOD_OP.split(".")
    assert getattr(getattr(bpy.ops, mod), name)() == {'FINISHED'}       # the dock's Flood button
    bpy.ops.allset.paint_skin_weights()                                  # leave the tool
    j3 = cyl.vertex_groups["joint3"].index
    w3 = [next((g.weight for g in v.groups if g.group == j3), 0.0) for v in cyl.data.vertices]
    assert max(_sums(cyl)) < 1.001 and min(w3) > 0.999, (max(_sums(cyl)), min(w3))


def test_flood_keeps_blender_choice_without_normalization():
    # Skin > Normalize Weights > Disable Weight Normalization: Flood just sets the weight (Maya normalizeWeights 0)
    _arm, cyl = _bound_cylinder()
    bpy.ops.allset.paint_skin_weights()
    ts = bpy.context.scene.tool_settings
    ts.use_auto_normalize = False
    cyl.vertex_groups.active_index = cyl.vertex_groups["joint3"].index
    _mod("compat").unified_paint_settings(ts).weight = 1.0
    ts.weight_paint.brush.weight = 1.0
    ts.weight_paint.brush.blend = 'MIX'
    mod, name = _mod("ui.paint_weights").FLOOD_OP.split(".")
    getattr(getattr(bpy.ops, mod), name)()
    bpy.ops.allset.paint_skin_weights()
    assert max(_sums(cyl)) > 1.5


# --- #19: switch to Blender in the template file (last: replaces the open file) ----------------------------------

def _strips(screen):
    return [a for a in screen.areas if a.type == 'IMAGE_EDITOR'
            and getattr(a.spaces.active, "mask", None) is not None and a.spaces.active.mask.name.startswith(".Allset")]


def _headerless_properties(screen):
    return [a for a in screen.areas if a.type == 'PROPERTIES' and not a.spaces.active.show_region_header]


def test_switch_to_blender_in_the_template_file():
    # In -b a Window.workspace assignment waits for an event loop that never runs, so this checks the data; the
    # screen itself is checked by tests/gui/gui_step129_switch_template.py. The Maya layout file is the
    # bundled one read as a new scene (no app template), File > New stays Blender's.
    sw = _mod("switch")
    _mod("first_start").new_maya_scene()
    win = bpy.context.window_manager.windows[0]
    assert sw.is_on() and sw.is_maya_workspace(win.workspace) and len(_strips(win.screen)) == 2
    n_ws = len(bpy.data.workspaces)
    sw.set_mode(False)
    layouts = [w for w in bpy.data.workspaces if sw.BLENDER_LAYOUT_KEY in w]
    assert len(layouts) == 1 and layouts[0].name == "Layout", [w.name for w in bpy.data.workspaces]
    assert not _strips(layouts[0].screens[0]) and not _headerless_properties(layouts[0].screens[0])
    assert bpy.context.preferences.app_template == ""
    sw.set_mode(True)
    sw.set_mode(False)
    # + Blender's own workspace for each Maya one named like Blender's (Sculpting -> "Sculpting (Maya)")
    n_own = len([w for w in bpy.data.workspaces if sw.MAYA_NAME_KEY in w])
    assert len(bpy.data.workspaces) == n_ws + 1 + n_own, "Blender's workspaces are appended once and reused"
    bpy.ops.wm.read_homefile()
    assert bpy.context.preferences.app_template == ""
    assert not _strips(bpy.context.window_manager.windows[0].screen)
