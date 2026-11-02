"""Graph Editor controls (#211): value lines (l), the w / e / r key tools, Unconstrained drag, Shift+drag on a
selected key and middle drags counted from the press."""

import math
from importlib import import_module
from types import SimpleNamespace

import bpy

import kit

gm = import_module(kit.MODULE + ".operators.graph_move")
gv = import_module(kit.MODULE + ".ui.graph_view")
sel = import_module(kit.MODULE + ".operators.select_2d")
prefs_mod = import_module(kit.MODULE + ".preferences")


def _cube_with_keys(keys=((1, 0.0), (10, 5.0), (20, 0.0))):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ob = bpy.data.objects.new("pCube1", bpy.data.meshes.new("pCubeShape1"))
    bpy.context.scene.collection.objects.link(ob)
    for f, v in keys:
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    fc = kit.fcurves(ob).find("location", index=0)
    for kp in fc.keyframe_points:
        kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
    fc.select = False
    return ob, fc


def _ctx(fcurves, normalized=False, value_lines=True):
    space = SimpleNamespace(type='GRAPH_EDITOR', mode='FCURVES', use_normalization=normalized)
    return SimpleNamespace(editable_fcurves=list(fcurves), visible_fcurves=list(fcurves), scene=bpy.context.scene,
                           space_data=space, preferences=bpy.context.preferences)


# --- pure rules ---------------------------------------------------------------------------------------------------

def test_scale_and_rotate_rules():
    assert gm.scale_factor(0) == 1.0
    assert gm.scale_factor(gm.SCALE_PX) == 2.0
    assert gm.scale_factor(-gm.SCALE_PX) == 0.0
    assert gm.scaled(14.0, 10.0, 0.5) == 12.0
    assert math.isclose(gm.rotate_angle(0, 10), math.radians(10 * gm.ROTATE_DEG_PER_PX))
    assert gm.rotate_angle(5, -5) == 0.0
    x, y = gm.rotate_offset(1.0, 0.0, math.cos(math.pi / 2), math.sin(math.pi / 2))
    assert abs(x) < 1e-9 and math.isclose(y, 1.0)
    assert gm.rotated_type('AUTO_CLAMPED') == 'ALIGNED' and gm.rotated_type('VECTOR') == 'ALIGNED'
    assert gm.rotated_type('FREE') == 'FREE' and gm.rotated_type('ALIGNED') == 'ALIGNED'


def test_value_line_rules():
    assert gv.value_range([]) is None
    assert gv.value_range([3.0, -1.0, 2.0]) == (-1.0, 3.0)
    _ob, fc = _cube_with_keys()
    assert gv.value_line_curves([fc]) == [fc]              # nothing selected: every curve shown
    _ob2 = bpy.data.objects["pCube1"]
    _ob2.location.y = 2.0
    _ob2.keyframe_insert("location", index=1, frame=1)
    fc_y = kit.fcurves(_ob2).find("location", index=1)
    for kp in fc_y.keyframe_points:
        kp.select_control_point = False
    fc_y.select = False
    fc.keyframe_points[1].select_control_point = True
    assert gv.value_line_curves([fc, fc_y]) == [fc]        # only the curve with a selected key


def test_value_lines_zero_min_max():
    _ob, fc = _cube_with_keys(((1, -2.0), (10, 5.0), (20, 1.0)))
    p = prefs_mod.get()
    old = p.graph_value_lines
    try:
        p.graph_value_lines = False
        assert gv.value_lines(_ctx([fc])) == []
        p.graph_value_lines = True
        lines = gv.value_lines(_ctx([fc]))
        assert [round(v, 6) for v, _c in lines] == [0.0, -2.0, 5.0], lines
        assert lines[0][1] == gv.ZERO_RGBA and lines[1][1] == gv.RANGE_RGBA
        # a single key value: one range line
        _ob, fc = _cube_with_keys(((1, 3.0),))
        assert [v for v, _c in gv.value_lines(_ctx([fc]))] == [0.0, 3.0]
        # no curves: the zero line only
        assert [v for v, _c in gv.value_lines(_ctx([]))] == [0.0]
        # other editors: nothing
        ctx = _ctx([fc])
        ctx.space_data.mode = 'DRIVERS'
        assert gv.value_lines(ctx) == []
    finally:
        p.graph_value_lines = old


def test_value_lines_toggle_operator():
    p = prefs_mod.get()
    old = p.graph_value_lines
    try:
        p.graph_value_lines = False
        assert bpy.ops.allset.graph_value_lines() == {'FINISHED'}
        assert p.graph_value_lines
        bpy.ops.allset.graph_value_lines()
        assert not p.graph_value_lines
    finally:
        p.graph_value_lines = old


# --- key tools --------------------------------------------------------------------------------------------------

def test_key_tool_operator_and_default():
    wm = bpy.context.window_manager
    assert wm.allset_graph_key_tool == 'MOVE'
    for tool in ('SCALE', 'ROTATE', 'MOVE'):
        assert bpy.ops.allset.graph_key_tool(tool=tool) == {'FINISHED'}
        assert wm.allset_graph_key_tool == tool


def test_unconstrained_drag_default_on():
    p = prefs_mod.get()
    assert type(p).bl_rna.properties["graph_unconstrained_drag"].default is True
    assert gm.unconstrained(bpy.context) == p.graph_unconstrained_drag


def test_keyset_scales_around_the_pivot():
    _ob, fc = _cube_with_keys()
    kp = fc.keyframe_points[1]
    kp.select_control_point = True
    kp.handle_left_type = kp.handle_right_type = 'FREE'
    left0, right0 = tuple(kp.handle_left), tuple(kp.handle_right)
    keys = gm.KeySet(_ctx([fc]))
    keys.apply_scale((6.0, 1.0), 2.0, 0.5, False)
    assert math.isclose(kp.co.x, 14.0) and math.isclose(kp.co.y, 3.0)
    assert math.isclose(kp.handle_left.x, 6.0 + (left0[0] - 6.0) * 2.0, abs_tol=1e-4)
    assert math.isclose(kp.handle_right.y, 1.0 + (right0[1] - 1.0) * 0.5, abs_tol=1e-4)
    # time snap: the key lands on a whole frame, its handles move with it
    keys.apply_scale((6.0, 1.0), 1.3, 1.0, True)       # 6 + 4 x 1.3 = 11.2 -> 11
    assert kp.co.x == 11.0
    assert math.isclose(kp.handle_left.x, 6.0 + (left0[0] - 6.0) * 1.3 - 0.2, abs_tol=1e-4)
    keys.restore()
    assert tuple(kp.co) == (10.0, 5.0)


def test_keyset_turns_tangents_only():
    _ob, fc = _cube_with_keys()
    kp = fc.keyframe_points[1]
    kp.select_control_point = True
    kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
    fc.update()
    kp = fc.keyframe_points[1]                         # update() may move the key array
    left, right = tuple(kp.handle_left), tuple(kp.handle_right)
    keys = gm.KeySet(_ctx([fc]))
    # 10 px per frame, 20 px per value unit: turn 90 deg counter-clockwise ((x, y) px -> (-y, x) px)
    keys.apply_rotate(math.pi / 2, 10.0, 20.0)
    assert tuple(kp.co) == (10.0, 5.0)
    assert kp.handle_left_type == kp.handle_right_type == 'ALIGNED', (kp.handle_left_type, kp.handle_right_type)
    for h, h0 in ((kp.handle_left, left), (kp.handle_right, right)):
        dx, dy = h0[0] - 10.0, h0[1] - 5.0
        # aligned handles: Blender lines the pair up again (a few 1/1000 of a frame)
        assert math.isclose(h.x, 10.0 - dy * 20.0 / 10.0, abs_tol=0.01), (tuple(h), h0)
        assert math.isclose(h.y, 5.0 + dx * 10.0 / 20.0, abs_tol=0.01), (tuple(h), h0)
    keys.restore()
    assert kp.handle_left_type == 'AUTO_CLAMPED'
    assert tuple(kp.co) == (10.0, 5.0)


# --- Shift+press on a selected key -------------------------------------------------------------------------------

def test_shift_press_selection_comes_back_for_the_drag():
    _ob, fc = _cube_with_keys()
    kp = fc.keyframe_points[1]
    kp.select_control_point = True
    before = sel.key_state()
    area = SimpleNamespace(as_pointer=lambda: 42)
    gm._SHIFT_PRESS["press"] = {"state": before, "pos": (100, 80), "area": 42}
    kp.select_control_point = False                    # Blender's Shift+click toggled it off on the press
    ctx = SimpleNamespace(area=area)
    assert gm.undo_shift_toggle(ctx, 100.4, 79.6)
    assert kp.select_control_point
    assert "press" not in gm._SHIFT_PRESS
    # another press position / editor: the toggle stands
    gm._SHIFT_PRESS["press"] = {"state": before, "pos": (100, 80), "area": 42}
    kp.select_control_point = False
    assert not gm.undo_shift_toggle(ctx, 140, 80)
    assert not kp.select_control_point
    gm._SHIFT_PRESS["press"] = {"state": before, "pos": (100, 80), "area": 7}
    assert not gm.undo_shift_toggle(ctx, 100, 80)
    assert not kp.select_control_point


# --- keymap --------------------------------------------------------------------------------------------------------

def test_keymap_items():
    km = kit.maya_kc().keymaps["Graph Editor"]
    items = [(i.idname, i.type, i.value, i.shift, i.ctrl, i.alt) for i in km.keymap_items if i.active]
    plain = lambda t, v='PRESS': [i[0] for i in items if i[1] == t and i[2] == v and not any(i[3:])]   # noqa: E731
    for key, tool in (("W", 'MOVE'), ("E", 'ROTATE'), ("R", 'SCALE')):
        assert plain(key) == ["allset.graph_key_tool"], (key, plain(key))
        it = next(i for i in km.keymap_items if i.idname == "allset.graph_key_tool" and i.type == key)
        assert it.properties.tool == tool
    assert plain("L") == ["allset.graph_value_lines"], plain("L")
    assert plain("MIDDLEMOUSE")[:1] == ["allset.graph_key_drag"], plain("MIDDLEMOUSE")
    shift_press = [i[0] for i in items if i[1] == 'LEFTMOUSE' and i[2] == 'PRESS' and i[3] and not i[4] and not i[5]]
    assert shift_press[0] == "allset.graph_shift_press", shift_press
    # Shift+MMB stays the axis-lock move
    assert ("allset.graph_axis_drag", 'MIDDLEMOUSE', 'PRESS', True, False, False) in items


def test_toolbar_and_menu_entries():
    ec = import_module(kit.MODULE + ".ui.editor_chrome")
    emm = import_module(kit.MODULE + ".ui.editor_menu_map")
    keys = {it[0]: it for it in ec.GRAPH_ICONS if isinstance(it, tuple)}
    # Maya's drag constraint button; the w / e / r key tools live in Edit > Transformation Tools (not the toolbar)
    assert keys["constrained_drag"][2] == ("prop", "addon_prefs.graph_unconstrained_drag", {})
    assert not {"moveKeysTool", "rotateKeysTool", "scaleKeysTool"} & set(keys)
    m = emm.MAP if hasattr(emm, "MAP") else None
    if m is not None:
        assert m["Graph Editor/Edit/Transformation Tools/Scale Keys Tool"][2] == {"value": 'SCALE'}
