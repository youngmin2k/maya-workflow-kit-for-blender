"""Step 271 (0.6.0 release QA): fixes found by the gate.

- Start-up in Maya mode registers with Blender's restricted data: the constraint helper lookup must not touch
  ``bpy.data.collections`` then (the start-up itself is checked by test_step130_lifecycle).
- Menu / marking-menu items whose Blender operator can't run warn or do nothing instead of raising."""

from importlib import import_module

import bpy

import kit

constrain_multi = import_module(kit.MODULE + ".operators.constrain_multi")


class _Restricted:
    """Stands for Blender's restricted ``bpy.data`` during add-on registration (no ID collections)."""


def test_helpers_with_restricted_data_finds_nothing():
    real = constrain_multi.bpy
    fake = type("FakeBpy", (), {"data": _Restricted()})()
    constrain_multi.bpy = fake
    try:
        assert constrain_multi.helpers() == []
    finally:
        constrain_multi.bpy = real
    assert constrain_multi.helpers() == []          # a real file without helpers


def test_pivot_reset_without_selection_does_nothing():
    bpy.ops.object.select_all(action='DESELECT')
    assert bpy.ops.allset.pivot_reset() == {'CANCELLED'}


def test_uv_prepare_with_hidden_active_mesh_does_not_raise():
    uv_tools = import_module(kit.MODULE + ".operators.uv_tools")
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.object
    ob.hide_set(True)
    bpy.context.view_layer.objects.active = ob
    assert uv_tools.prepare(bpy.context) is False
    assert ob.mode == 'OBJECT'


def test_interp_with_zero_scaled_parent_frame_skips():
    from mathutils import Matrix
    ci = import_module(kit.MODULE + ".operators.constrain_interp")
    real = ci.parent_frame
    ci.parent_frame = lambda _owner: Matrix.Diagonal((0.0, 0.0, 0.0))
    try:
        assert ci.target_quats(None, "") is None       # no ValueError from inverting a zero frame
    finally:
        ci.parent_frame = real
