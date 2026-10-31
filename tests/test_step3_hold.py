"""Hold keys, tap/hold framework, pivot toggle, pick-walk."""

import sys
from importlib import import_module

import bpy

import kit

hold = import_module(kit.MODULE + ".operators.hold")
taphold = import_module(kit.MODULE + ".operators.taphold")
pickwalk = import_module(kit.MODULE + ".operators.pickwalk")
keystate = import_module(kit.MODULE + ".operators.keystate")
maya_patches = import_module(kit.MODULE + ".keymap.maya_patches")


def _ts():
    return bpy.context.scene.tool_settings


def _kmis(km_name, type, shift=False, ctrl=False, alt=False):
    km = kit.maya_kc().keymaps[km_name]
    return [k for k in km.keymap_items if k.active and k.type == type and k.value == 'PRESS'
            and k.shift == shift and k.ctrl == ctrl and k.alt == alt and not k.oskey]


# --- hold manager -------------------------------------------------------------

def test_hold_snap_sets_and_restores():
    ts = _ts()
    ts.use_snap, ts.snap_elements = False, {'FACE'}
    hold.begin(ts, "grid")
    assert ts.use_snap and set(ts.snap_elements) == {'GRID'}
    hold.end(ts, "grid")
    assert not ts.use_snap and set(ts.snap_elements) == {'FACE'}
    assert hold.active_holds() == {}


def test_hold_snap_union_and_out_of_order_release():
    ts = _ts()
    ts.use_snap, ts.snap_elements = True, {'INCREMENT'}
    hold.begin(ts, "grid")
    hold.begin(ts, "point")
    assert set(ts.snap_elements) == {'GRID', 'VERTEX'}
    hold.begin(ts, "point")  # duplicate begin (key repeat) is harmless
    hold.end(ts, "grid")     # release in a different order than pressed
    assert ts.use_snap and set(ts.snap_elements) == {'VERTEX'}
    hold.end(ts, "point")
    assert ts.use_snap and set(ts.snap_elements) == {'INCREMENT'}
    hold.end(ts, "point")    # stray release: no effect
    assert set(ts.snap_elements) == {'INCREMENT'}


def test_hold_each_snap_name_maps_to_elements():
    ts = _ts()
    want = {"grid": {'GRID'}, "curve": {'EDGE'}, "point": {'VERTEX'}, "step": {'INCREMENT'}}
    for name, elements in want.items():
        hold.begin(ts, name)
        assert set(ts.snap_elements) == elements, name
        hold.end(ts, name)


def test_hold_pivot_independent_of_snap():
    ts = _ts()
    ts.use_transform_data_origin = False
    ts.use_snap = False
    hold.begin(ts, "pivot")
    hold.begin(ts, "grid")
    assert ts.use_transform_data_origin and ts.use_snap
    hold.end(ts, "pivot")
    assert not ts.use_transform_data_origin and ts.use_snap
    hold.end(ts, "grid")
    assert not ts.use_snap


def test_end_all_restores():
    ts = _ts()
    ts.use_snap = False
    ts.use_transform_data_origin = False
    hold.begin(ts, "grid")
    hold.begin(ts, "pivot")
    hold.end_all(ts)
    assert not ts.use_snap and not ts.use_transform_data_origin and hold.active_holds() == {}


def test_disable_mid_hold_restores_state():
    ts = _ts()
    ts.use_snap = False
    hold.begin(ts, "grid")
    kit.disable()
    try:
        assert not _ts().use_snap
    finally:
        kit.enable()


def test_keystate():
    assert keystate.vk_code("X") == ord("X") and keystate.vk_code("INSERT") == 0x2D
    state = keystate.is_down("X")
    if sys.platform == "win32":
        assert state is False  # nobody is pressing X during the test run
    else:
        assert state is None
    assert keystate.is_down("NDOF_BUTTON_1") is None


# --- operators ----------------------------------------------------------------

def test_pivot_toggle():
    ts = _ts()
    ts.use_transform_data_origin = False
    assert bpy.ops.allset.pivot_toggle() == {'FINISHED'}
    assert ts.use_transform_data_origin
    bpy.ops.allset.pivot_toggle()
    assert not ts.use_transform_data_origin


def test_tap_hold_registry():
    assert {"soft_select", "select_all"} <= set(taphold.binding_names())
    assert isinstance(taphold.get_binding("soft_select"), taphold.TapHoldBinding)


class _Ctx:
    """Minimal stand-in for bpy.context inside binding callbacks."""
    def __init__(self, mode):
        self.mode = mode
        self.scene = bpy.context.scene
        self.area = None


class _Ev:
    def __init__(self, x):
        self.mouse_x, self.mouse_y = x, 0


def test_soft_select_tap_toggles_one_state():
    """#15: one Maya state, both Blender flags follow it (was per mode)."""
    ts = _ts()
    b = taphold.get_binding("soft_select")
    ts.use_proportional_edit_objects = False
    ts.use_proportional_edit = False
    b.tap(_Ctx('OBJECT'))
    assert ts.use_proportional_edit_objects and ts.use_proportional_edit
    b.tap(_Ctx('EDIT_MESH'))
    assert not ts.use_proportional_edit and not ts.use_proportional_edit_objects
    b.tap(_Ctx('OBJECT'))
    assert ts.use_proportional_edit_objects and ts.use_proportional_edit
    b.tap(_Ctx('OBJECT'))


def test_soft_select_drag_and_cancel():
    ts = _ts()
    b = taphold.get_binding("soft_select")
    ts.proportional_size = 2.0
    ts.use_proportional_edit_objects = False
    ctx = _Ctx('OBJECT')
    assert b.click(ctx, _Ev(500)) == 'DRAG'
    assert ts.use_proportional_edit_objects, "drag turns soft select on"
    b.drag(ctx, _Ev(600), (500, 0))
    assert abs(ts.proportional_size - 4.0) < 1e-5, ts.proportional_size
    b.drag(ctx, _Ev(400), (500, 0))
    assert abs(ts.proportional_size - 1.0) < 1e-5
    b.drag_cancel(ctx)
    assert abs(ts.proportional_size - 2.0) < 1e-5 and not ts.use_proportional_edit_objects
    assert taphold.radius_from_drag(1.0, -100000) > 0


# --- pick-walk ----------------------------------------------------------------

def _obj(name, parent=None):
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = parent
    return ob


def _select(objs, active=None):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


def _selected():
    return sorted(o.name for o in bpy.context.selected_objects)


def test_pick_walk():
    root = _obj("pw_root")
    b, a, c = _obj("pw_b", root), _obj("pw_a", root), _obj("pw_c", root)
    leaf = _obj("pw_leaf", a)
    vl = bpy.context.view_layer
    vl.update()  # sync new objects into view_layer.objects
    assert pickwalk.walk(vl, a, "UP") == root
    # creation order b, a, c: Maya walks down to the first child made
    assert pickwalk.walk(vl, root, "DOWN") == b          # the first child made
    assert pickwalk.walk(vl, b, "RIGHT") == a
    assert pickwalk.walk(vl, a, "RIGHT") == c
    assert pickwalk.walk(vl, c, "RIGHT") == b            # wraps
    assert pickwalk.walk(vl, b, "LEFT") == c             # wraps backwards
    assert pickwalk.walk(vl, leaf, "DOWN") == leaf       # nowhere to go
    assert pickwalk.walk(vl, leaf, "LEFT") == leaf       # only child
    assert pickwalk.walk(vl, root, "UP") == root         # already at the top

    _select([leaf])
    assert bpy.ops.allset.pick_walk(direction="UP") == {'FINISHED'}
    assert _selected() == ["pw_a"] and vl.objects.active == a
    _select([a, b], active=b)
    bpy.ops.allset.pick_walk(direction="UP")
    assert _selected() == ["pw_root"], _selected()       # both walk to the same parent
    _select([a, b], active=b)
    bpy.ops.allset.pick_walk(direction="RIGHT")
    assert _selected() == ["pw_a", "pw_c"] and vl.objects.active == a   # creation order b, a, c


# --- keymap ---------------------------------------------------------------------

def test_hold_keys_bound():
    for key, name in maya_patches.HOLD_KEYS:
        for shift in (False, True):
            items = _kmis("3D View", key, shift=shift)
            assert [(k.idname, k.properties.name) for k in items] == [("allset.hold", name)], \
                (key, shift, [k.idname for k in items])
    for km in ("Object Mode", "Mesh", "Curve", "Armature", "Metaball"):
        assert _kmis(km, "C") == [], km     # cursor tool removed so the 3D View hold runs


def test_soft_select_and_select_all_keys():
    assert [k.properties.binding for k in _kmis("3D View", "B")] == ["soft_select"]
    assert [k.properties.binding for k in _kmis("3D View", "A")] == ["select_all"]
    for km in ("Object Mode", "Mesh", "Curve", "Lattice"):
        assert _kmis(km, "B") == [], km
    # Paint modes keep their own B (brush shelf).
    assert _kmis("Sculpt", "B")


def test_pivot_and_pick_walk_keys():
    assert [k.properties.name for k in _kmis("Object Mode", "D")] == ["pivot"]
    assert [k.idname for k in _kmis("Object Mode", "INSERT")] == ["allset.pivot_toggle"]
    for key, direction in maya_patches.PICK_WALK_KEYS:
        items = _kmis("Object Mode", key)
        assert [(k.idname, k.properties.direction) for k in items] == \
            [("allset.pick_walk", direction)], key
    # Pose mode arrows walk joints (frames: Alt+, / Alt+.); other modes keep IC's.
    assert [k.idname for k in _kmis("Pose", "LEFT_ARROW")] == ["allset.pick_walk_joint"]


def test_hold_operator_refuses_non_press():
    # Invoked without a PRESS event (e.g. from Python) it must not start a modal.
    assert bpy.ops.allset.hold('EXEC_DEFAULT', name="grid") != {'RUNNING_MODAL'}
