"""One Maya soft select state (#15, #1), B + MMB radius drag (#1), falloff colour overlay (#2).
GUI: tests/gui/gui_step129_soft_select.py."""

import os
import tempfile
import time
from importlib import import_module

import bmesh
import bpy
import numpy as np

import kit

taphold = import_module(kit.MODULE + ".operators.taphold")
soft = import_module(kit.MODULE + ".operators.soft_select")
overlay = import_module(kit.MODULE + ".ui.soft_overlay")
mtk = import_module(kit.MODULE + ".ui.modeling_toolkit")


def _ts():
    return bpy.context.scene.tool_settings


class _Ctx:
    def __init__(self, mode):
        self.mode = mode
        self.scene = bpy.context.scene
        self.area = None


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _grid(n=21, size=2.0, name="grid"):
    """An n x n vertex grid in edit mode, the middle vertex selected."""
    _clear()
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=n - 1, y_segments=n - 1, size=size / 2)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for o in bpy.context.scene.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(me)
    centre = min(bm.verts, key=lambda v: v.co.length)
    for v in bm.verts:
        v.select = v is centre
    bm.select_flush(False)
    bmesh.update_edit_mesh(me)
    return ob


def _coords(ob):
    bm = bmesh.from_edit_mesh(ob.data)
    return np.array([v.co[:] for v in bm.verts])


# --- one state (#15) ------------------------------------------------------------------------

def test_maya_mode_starts_off():
    assert soft.is_on() is False, "soft select starts off"


def test_b_tap_is_one_state_in_object_and_component_mode():
    soft.set_on(False)
    b = taphold.get_binding("soft_select")
    b.tap(_Ctx('OBJECT'))
    ts = _ts()
    assert ts.use_proportional_edit_objects and ts.use_proportional_edit, "B in object mode = on everywhere"
    assert soft.is_on()
    b.tap(_Ctx('EDIT_MESH'))
    assert not ts.use_proportional_edit_objects and not ts.use_proportional_edit, "B in face mode = off everywhere"


def test_every_scene_follows():
    soft.set_on(False)
    other = bpy.data.scenes.new("other")
    try:
        soft.set_on(True)
        assert other.tool_settings.use_proportional_edit and other.tool_settings.use_proportional_edit_objects
    finally:
        bpy.data.scenes.remove(other)
        soft.set_on(False)


def test_blender_toggle_is_pulled_into_the_state():
    soft.set_on(False)
    ts = _ts()
    ts.use_proportional_edit = True            # Blender's header button / wm.context_toggle in edit mode
    soft.pull(bpy.context.scene)
    assert soft.is_on() and ts.use_proportional_edit_objects
    ts.use_proportional_edit_objects = False   # ... and off in object mode
    soft.pull(bpy.context.scene)
    assert not soft.is_on() and not ts.use_proportional_edit


def test_toolkit_checkbox_is_the_state():
    soft.set_on(False)
    sc = bpy.context.scene
    sc.allset_soft_select = True
    assert soft.is_on() and sc.tool_settings.use_proportional_edit_objects and sc.tool_settings.use_proportional_edit
    sc.allset_soft_select = False
    assert not soft.is_on()


def test_a_file_saved_with_soft_select_on_follows_the_global_state():
    soft.set_on(True)
    path = os.path.join(tempfile.mkdtemp(prefix="allset129"), "soft_on.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
    soft.set_on(False)
    bpy.ops.wm.open_mainfile(filepath=path)
    ts = bpy.context.scene.tool_settings
    assert not ts.use_proportional_edit and not ts.use_proportional_edit_objects, "Maya: a global option"


def test_b_drag_turns_on_both_and_cancel_restores():
    soft.set_on(False)
    b = taphold.get_binding("soft_select")
    ts = _ts()
    ts.proportional_size = 2.0

    class _Ev:
        def __init__(self, x):
            self.mouse_x, self.mouse_y = x, 0
            self.mouse_region_x, self.mouse_region_y = x, 0

    ctx = _Ctx('EDIT_MESH')
    assert b.click(ctx, _Ev(500)) == 'DRAG'
    assert ts.use_proportional_edit and ts.use_proportional_edit_objects
    b.drag(ctx, _Ev(600), (500, 0))
    assert abs(ts.proportional_size - 4.0) < 1e-5
    b.drag_cancel(ctx)
    assert abs(ts.proportional_size - 2.0) < 1e-5 and not soft.is_on() and not ts.use_proportional_edit


def test_b_drags_with_lmb_and_mmb():
    """Maya: B + LMB **or** MMB drag."""
    assert taphold.get_binding("soft_select").buttons == {'LEFTMOUSE', 'MIDDLEMOUSE'}
    assert taphold.get_binding("select_all").buttons == {'LEFTMOUSE'}


# --- colours (#2) ----------------------------------------------------------------------------

def test_maya_colour_ramp():
    """Falloff colour curve 1,1,0,1,1, 1,0,0,0.5,1, 0,0,0,0,1 (r, g, b, position, linear)."""
    c = soft.ramp(np.array([1.0, 0.75, 0.5, 0.25, 0.0]))
    want = [(1, 1, 0), (1, 0.5, 0), (1, 0, 0), (0.5, 0, 0), (0, 0, 0)]
    assert np.allclose(c, want), c


def _check_against_transform(falloff, connected, radius=0.55):
    ob = _grid()
    ts = _ts()
    ts.proportional_edit_falloff = falloff
    ts.proportional_size = radius
    ts.use_proportional_connected = connected
    ts.use_proportional_projected = False
    w = overlay.object_weights(ob, ts)
    before = _coords(ob)
    bpy.ops.transform.translate(value=(0, 0, 1), use_proportional_edit=True, proportional_edit_falloff=falloff,
                                proportional_size=radius, use_proportional_connected=connected,
                                use_proportional_projected=False)
    moved = _coords(ob)[:, 2] - before[:, 2]
    bad = np.flatnonzero(np.abs(moved - w) > 1e-4)
    assert bad.size == 0, (falloff, connected, [(int(i), float(moved[i]), float(w[i])) for i in bad[:8]])
    assert (w > 0).sum() > 5


def test_weights_equal_blender_transform_volume():
    for f in ('SMOOTH', 'SPHERE', 'ROOT', 'INVERSE_SQUARE', 'SHARP', 'LINEAR', 'CONSTANT'):
        _check_against_transform(f, False)


def test_weights_equal_blender_transform_surface():
    for f in ('SMOOTH', 'LINEAR'):
        _check_against_transform(f, True)


def test_projected_distance_ignores_depth():
    co = np.array([[0, 0, 0], [0, 0, 5.0], [0.5, 0, 0]])
    sel = np.array([True, False, False])
    d = soft.distances(co, sel, 1.0, view_axis=(0, 0, 1))
    assert abs(d[1]) < 1e-9 and abs(d[2] - 0.5) < 1e-9
    d = soft.distances(co, sel, 1.0)
    assert np.isinf(d[1]) or d[1] > 1.0


def test_overlay_handlers_registered():
    assert overlay._handles, "POST_VIEW / POST_PIXEL draw handlers"


def test_dense_mesh_speed():
    ob = _grid(n=317, size=20.0, name="dense")     # 100,489 vertices
    ts = _ts()
    ts.proportional_edit_falloff = 'SMOOTH'
    ts.use_proportional_connected = False
    ts.proportional_size = 3.0
    overlay.invalidate_all()
    t0 = time.perf_counter()
    w = overlay.object_weights(ob, ts)
    first = time.perf_counter() - t0
    t0 = time.perf_counter()
    overlay.object_weights(ob, ts)
    cached = time.perf_counter() - t0
    ts.proportional_size = 4.0
    t0 = time.perf_counter()
    overlay.object_weights(ob, ts)
    radius = time.perf_counter() - t0
    ts.use_proportional_connected = True
    t0 = time.perf_counter()
    overlay.object_weights(ob, ts)
    surface = time.perf_counter() - t0
    print(f"dense {len(w)} verts: first {first:.3f}s cached {cached * 1000:.2f}ms radius {radius:.3f}s "
          f"surface {surface:.3f}s affected {(w > 0).sum()}")
    assert first < 2.0 and cached < 0.005 and radius < 0.5 and surface < 2.0
