"""Issue #264: a Maya-style manipulator in the UV Editor. The UV Editor's Move / Rotate / Scale tools use the kit's
handles (U / V arrows and a centre square, one ring, U / V box handles and a centre box) at the centre of the
selected UVs' box; each handle starts Blender's transform along its axis. Disabling the extension gives the tools
Blender's gizmos back."""

from importlib import import_module

import bmesh
import bpy

import kit

um = import_module(kit.MODULE + ".ui.uv_manipulator")


def _widgets():
    from bl_ui.space_toolsystem_toolbar import IMAGE_PT_tools_active
    return {it.idname: it.widget for it in um._flat(IMAGE_PT_tools_active._tools['UV']) if it.idname in um.TOOLS}


def test_uv_tools_use_the_kit_manipulator():
    assert _widgets() == {t: um.GROUP for t in um.TOOLS}, _widgets()
    assert "bl_rna" in um.ALLSET_GGT_uv_xform.__dict__ and "bl_rna" in um.ALLSET_GT_uv_handle.__dict__   # registered


def test_disable_gives_blender_gizmos_back():
    kit.disable()
    try:
        w = _widgets()
        assert w == {"builtin.move": "IMAGE_GGT_gizmo2d_translate", "builtin.rotate": "IMAGE_GGT_gizmo2d_rotate",
                     "builtin.scale": "IMAGE_GGT_gizmo2d_resize"}, w
    finally:
        kit.enable()
    assert _widgets() == {t: um.GROUP for t in um.TOOLS}


def test_preference_off_gives_blender_gizmos_back():
    prefs = import_module(kit.MODULE + ".preferences").get()
    blender = {"builtin.move": "IMAGE_GGT_gizmo2d_translate", "builtin.rotate": "IMAGE_GGT_gizmo2d_rotate",
               "builtin.scale": "IMAGE_GGT_gizmo2d_resize"}
    assert prefs.maya_uv_manipulator, "on by default"
    prefs.maya_uv_manipulator = False
    try:
        assert _widgets() == blender, _widgets()
        um._ensure_timer()      # the watch timer keeps Blender's gizmos while the preference is off
        assert _widgets() == blender, _widgets()
    finally:
        prefs.maya_uv_manipulator = True
    assert _widgets() == {t: um.GROUP for t in um.TOOLS}


def test_handles_are_picked_by_screen_distance():
    L = 80.0
    assert um.hit('TRANSLATE', 'U', 60, 2, L) and not um.hit('TRANSLATE', 'U', 2, 60, L)
    assert um.hit('TRANSLATE', 'V', 3, 70, L) and not um.hit('TRANSLATE', 'V', 70, 3, L)
    assert um.hit('TRANSLATE', 'UV', 4, -5, L)
    assert not um.hit('TRANSLATE', 'U', 4, -5, L), "the centre square is not the U arrow"
    assert um.hit('ROTATE', 'UV', 0, 79, L) and not um.hit('ROTATE', 'UV', 0, 40, L)
    assert um.hit('RESIZE', 'U', 78, 0, L) and not um.hit('RESIZE', 'U', 120, 0, L)


def test_handles_start_blender_transforms_along_their_axis():
    assert um.OPS == {'TRANSLATE': "transform.translate", 'ROTATE': "transform.rotate",
                      'RESIZE': "transform.resize"}
    assert um.AXES['U'] == (True, False, False) and um.AXES['V'] == (False, True, False)


def test_selected_uv_bounds():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.mesh.primitive_plane_add()
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    ts = bpy.context.scene.tool_settings
    ts.use_uv_select_sync = True
    bpy.ops.mesh.select_all(action='SELECT')
    b = um.selected_uv_bounds(bpy.context)
    assert b is not None and all(abs(x - y) < 1e-5 for x, y in zip(b, (0, 0, 1, 1))), b
    bm = bmesh.from_edit_mesh(ob.data)
    for v in bm.verts:
        v.select = False
    bm.select_flush(False)
    bmesh.update_edit_mesh(ob.data)
    assert um.selected_uv_bounds(bpy.context) is None
    bpy.ops.object.mode_set(mode='OBJECT')
