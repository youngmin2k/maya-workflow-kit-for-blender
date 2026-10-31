"""Maya display / mode keys leave no Adjust Last Operation panel (#58), and Smooth Mesh
Preview (3) is smooth shaded on Maya primitives whose hard edges are sharp_edge (#61)."""

from importlib import import_module

import bpy

import kit

display = import_module(kit.MODULE + ".operators.display")

# Blender shows the redo panel only for an operator with REGISTER *and* UNDO (WM_operator_last_redo);
# UNDO alone pushes the undo step and clears the panel (wm_operator_finished, hud_status CLEAR).
NO_HUD = ("allset.display_mode", "allset.smooth_preview", "allset.smooth_level", "allset.component_mode",
          "allset.component_mask", "allset.toggle_sel_mode", "allset.select_mode", "allset.mm_component",
          "allset.uv_component", "allset.cycle_display", "allset.camera_mode_toggle", "allset.symmetry",
          "allset.cycle_background", "allset.toggle_grid", "allset.pivot_toggle")
# Maya keeps these in its undo queue (component mode = hilite)
# or Blender needs the push so a later undo doesn't drop the change (smooth preview).
KEEP_UNDO = ("allset.smooth_preview", "allset.smooth_level", "allset.component_mode", "allset.component_mask",
             "allset.toggle_sel_mode", "allset.select_mode")
KEYS = {"ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "F7", "F8", "F9", "F10", "F11", "PAGE_UP",
        "PAGE_DOWN"}
ALT_KEYS = {"A", "B", "P", "R"}
KEYMAPS = ("3D View", "Object Mode", "Object Non-modal", "Mesh", "Window", "Screen")


def _cls(idname):
    mod, name = idname.split(".")
    return getattr(bpy.types, f"{mod.upper()}_OT_{name}")


def _shows_hud(idname):
    opts = _cls(idname).bl_options
    return 'REGISTER' in opts and 'UNDO' in opts


def test_display_and_mode_operators_have_no_redo_panel():
    bad = [i for i in NO_HUD if _shows_hud(i)]
    assert not bad, f"these would open Adjust Last Operation: {bad}"
    lost = [i for i in KEEP_UNDO if 'UNDO' not in _cls(i).bl_options]
    assert not lost, f"lost their undo step: {lost}"


def test_maya_display_keys_bind_no_redo_operator():
    seen, bad = [], []
    kc = kit.maya_kc()
    for name in KEYMAPS:
        km = kc.keymaps.get(name)
        if km is None:
            continue
        for it in km.keymap_items:
            if not it.active or not it.idname.startswith("allset."):
                continue
            mods = (it.shift, it.ctrl, it.alt, it.oskey)
            plain = it.type in KEYS and not any(m == 1 for m in mods)
            alt = it.type in ALT_KEYS and it.alt == 1 and not (it.shift == 1 or it.ctrl == 1)
            if not (plain or alt):
                continue
            seen.append((name, it.type, it.idname))
            if it.idname in ("allset.tap_hold", "allset.hold"):
                continue
            if _shows_hud(it.idname):
                bad.append((name, it.type, it.idname))
    assert any(t == "THREE" for _n, t, _i in seen) and any(t == "F9" for _n, t, _i in seen), seen
    assert not bad, bad


def _clear():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)


def _maya_cube():
    _clear()
    assert bpy.ops.allset.create(kind='CUBE') == {'FINISHED'}
    return bpy.context.active_object


def _eval(ob):
    bpy.context.view_layer.update()
    return ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data


def _bools(me, name):
    a = me.attributes.get(name)
    if a is None:
        return []
    return [d.value for d in a.data]


def _smooth_shaded(me):
    """No sharp face / edge and point normals: every corner of a vertex shares one normal."""
    return (not any(_bools(me, "sharp_edge")) and not any(_bools(me, "sharp_face"))
            and me.normals_domain == 'POINT')


def test_maya_cube_has_hard_edges():
    # The input of #61: Maya's polyCube keeps its hard edges as sharp_edge (prim_history.fill_bmesh).
    ob = _maya_cube()
    me = ob.data
    assert len(me.vertices) == 8 and all(_bools(me, "sharp_edge")), _bools(me, "sharp_edge")
    assert me.normals_domain != 'POINT', me.normals_domain


def test_smooth_preview_is_smooth_shaded_on_a_maya_cube():
    ob = _maya_cube()
    assert bpy.ops.allset.smooth_preview(level=3) == {'FINISHED'}
    me = _eval(ob)
    assert len(me.vertices) > 8, len(me.vertices)
    assert _smooth_shaded(me), (sum(_bools(me, "sharp_edge")), sum(_bools(me, "sharp_face")), me.normals_domain)
    # Corner normals of one face differ (curved), unlike a faceted face where all four are the face normal.
    p = me.polygons[0]
    ns = [me.corner_normals[i].vector for i in p.loop_indices]
    assert max((n - p.normal).length for n in ns) > 0.05, [tuple(n) for n in ns]
    assert all(_bools(ob.data, "sharp_edge")), "mesh data untouched: hard edges kept"


def test_one_is_faceted_again():
    ob = _maya_cube()
    bpy.ops.allset.smooth_preview(level=3)
    bpy.ops.allset.smooth_preview(level=1)
    me = _eval(ob)
    assert len(me.vertices) == 8 and all(_bools(me, "sharp_edge")) and me.normals_domain != 'POINT'


def test_two_is_smooth_with_the_cage():
    ob = _maya_cube()
    bpy.ops.allset.smooth_preview(level=2)
    me = _eval(ob)
    assert len(me.vertices) > 8 and _smooth_shaded(me) and ob.show_wire


def test_old_face_only_group_is_upgraded():
    # A 0.2.x file has the face-only shading group: pressing 3 again rebuilds it in place.
    _clear()
    old = bpy.data.node_groups.get(display.SHADE_GROUP_NAME)
    if old is not None:
        bpy.data.node_groups.remove(old)
    ng = bpy.data.node_groups.new(display.SHADE_GROUP_NAME, 'GeometryNodeTree')
    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gin, gout = ng.nodes.new("NodeGroupInput"), ng.nodes.new("NodeGroupOutput")
    smooth = ng.nodes.new("GeometryNodeSetShadeSmooth")
    ng.links.new(gin.outputs[0], smooth.inputs["Geometry"])
    ng.links.new(smooth.outputs[0], gout.inputs[0])
    bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    shade = ob.modifiers.new(display.PREVIEW_SHADE_NAME, 'NODES')
    shade.node_group = ng
    sub = ob.modifiers.new(display.PREVIEW_MOD_NAME, 'SUBSURF')
    sub.levels = 2
    assert not _smooth_shaded(_eval(ob)), "the old group leaves the Maya cube faceted (#61)"
    bpy.ops.allset.smooth_preview(level=3)
    assert ob.modifiers[display.PREVIEW_SHADE_NAME].node_group == ng
    assert len([g for g in bpy.data.node_groups if g.name.startswith(display.SHADE_GROUP_NAME)]) == 1
    assert _smooth_shaded(_eval(ob))


def test_component_mode_and_preview_still_undo():
    # Maya undoes a component-mode change (hilite); the kit keeps the undo push for F9 and 3.
    ob = _maya_cube()
    assert 'UNDO' in _cls("allset.component_mode").bl_options
    assert 'UNDO' in _cls("allset.smooth_preview").bl_options
    assert bpy.ops.allset.component_mode(type='VERT') == {'FINISHED'}
    assert bpy.context.mode == 'EDIT_MESH'
    bpy.ops.object.mode_set(mode='OBJECT')
    assert ob.name in bpy.context.scene.objects
