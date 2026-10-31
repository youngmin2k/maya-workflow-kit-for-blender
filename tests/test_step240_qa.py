"""Release QA, activity J: tests for mutants that survived the mutation sample (tools/qa/qa_mutants.py).

- status_line.snap_on must read Blender's use_snap: an element left in snap_elements while snapping is off is not "on"
  (the Status Line icon would show on while Move doesn't snap, #139 class).
- Animation layer weights (Maya: additive = base + w·x, override = lerp, scale layers multiply by x^w; quaternion
  additive = lower @ q^w) — layer weights other than 1 were not exercised.
- Outliner rows (QA G): the parent → children map keeps Maya DAG order.
"""

import math
from importlib import import_module

import bpy

import kit

anim_layers = import_module(kit.MODULE + ".operators.anim_layers")
status_line = import_module(kit.MODULE + ".ui.status_line")
outliner = import_module(kit.MODULE + ".ui.outliner")


def test_snap_icon_off_when_snapping_is_off():
    ts = bpy.context.scene.tool_settings
    ts.snap_elements = {'GRID'}
    ts.use_snap = False
    assert not status_line.snap_on(ts, "GRID"), "grid icon shows on while Blender snapping is off"
    ts.use_snap = True
    assert status_line.snap_on(ts, "GRID")
    ts.use_snap = False


def test_layer_weights_compose_like_maya():
    c = anim_layers.compose
    assert math.isclose(c([('ADD', 0.5, 10.0)], 2.0), 7.0)              # additive: base + w * x
    assert math.isclose(c([('REPLACE', 0.25, 10.0)], 2.0), 4.0)         # override: lerp
    assert math.isclose(c([('MUL', 0.5, 4.0)], 3.0), 6.0)               # scale: base * x ** w
    assert math.isclose(c([('ADD', 1.0, 1.0), ('REPLACE', 0.5, 0.0), ('ADD', 0.5, 2.0)], 1.0), 2.0)


def test_quaternion_layer_weight():
    from mathutils import Quaternion
    q90 = Quaternion((0, 0, 1), math.radians(90))
    out = anim_layers.compose_quaternion([("L", 'COMBINE', 0.5, q90)], (1, 0, 0, 0))
    assert math.isclose(math.degrees(out.angle), 45.0, abs_tol=1e-4), math.degrees(out.angle)
    out = anim_layers.compose_quaternion([("L", 'REPLACE', 0.5, q90)], (1, 0, 0, 0))
    assert math.isclose(out.normalized().angle, math.radians(45), abs_tol=1e-4)


def test_outliner_rows_keep_dag_order():
    scene = bpy.context.scene
    obs = []
    for name in ("qaA", "qaB", "qaC", "qaD"):
        ob = bpy.data.objects.new(name, None)
        scene.collection.objects.link(ob)
        obs.append(ob)
    a, b, c, d = obs
    c.parent = a
    d.parent = a
    for ob in obs:
        ob.allset_expanded = True
    rows = [r[1] for r in outliner.dag_rows(scene, False) if r[1].startswith("qa")]
    assert rows == ["qaA", "qaC", "qaD", "qaB"], rows
    bpy.data.batch_remove(obs)


# --- S2 fixes found by the new QA activities ------------------------------------------------------------------

def test_circularize_from_object_mode():
    """D-240-1: Edit Mesh > Circularize with an object selected raised TypeError (an old LoopTools "value" key)."""
    bpy.ops.mesh.primitive_cube_add()
    ob = bpy.context.active_object
    assert bpy.ops.allset.menu_whole_mesh(item="Edit Mesh/Circularize") == {'FINISHED'}
    assert ob.mode == 'OBJECT'
    bpy.data.objects.remove(ob)


def test_step_snap_off_stays_off_when_the_grid_goes():
    """C-240-1: Scale Step Absolute, Grid on, Rotate Step Off, Grid off -> Rotate showed Off but still stepped."""
    snap_align = import_module(kit.MODULE + ".operators.snap_align")
    ts = bpy.context.scene.tool_settings
    ts.use_snap, ts.snap_elements = False, {'INCREMENT'}
    ts.use_snap_translate = ts.use_snap_rotate = ts.use_snap_scale = True
    bpy.context.scene.pop(snap_align.STEP_PROP, None)
    snap_align.set_step_snap(ts, 'RESIZE', 'ABSOLUTE')
    status_line.toggle_snap(ts, "GRID")
    snap_align.set_step_snap(ts, 'ROTATE', 'OFF')
    assert ts.use_snap_rotate, "grid snap must still rotate-snap while it is on (#139)"
    status_line.toggle_snap(ts, "GRID")
    assert snap_align.step_snap_mode(ts, 'ROTATE') == 'OFF'
    stepping = ts.use_snap and 'INCREMENT' in ts.snap_elements and ts.use_snap_rotate
    assert not stepping, "Rotate shows Step Snap Off but Blender still steps it"
    assert snap_align.step_snap_mode(ts, 'RESIZE') == 'ABSOLUTE'


def test_undo_keeps_the_current_time():
    """H2-1: Maya's undo never moves the current time."""
    time_slider = import_module(kit.MODULE + ".ui.time_slider")
    scene = bpy.context.scene
    scene.frame_current = 12
    time_slider._keep_frame_pre()
    scene.frame_current = 1                      # what Blender's memfile undo does
    time_slider.restore_frame()
    assert scene.frame_current == 12


def test_uv_pin_geometry_waits_in_edit_mode():
    """D-240-2: the UV Pin depsgraph handler read the original mesh's UVs in edit mode (empty) on every update."""
    pins = import_module(kit.MODULE + ".operators.pins_205")
    bpy.ops.mesh.primitive_plane_add()
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        geo = pins.Geo(ob, bpy.context.evaluated_depsgraph_get())
        assert not geo.ok
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
    assert pins.Geo(ob, bpy.context.evaluated_depsgraph_get()).ok
    bpy.data.objects.remove(ob)
