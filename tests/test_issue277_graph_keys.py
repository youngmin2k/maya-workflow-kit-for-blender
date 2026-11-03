"""Graph Editor look (#277): keys drawn bigger than Blender's theme size (a rim around each key Blender draws, in
its own colour) and toolbar buttons that don't share one icon."""

import math
from importlib import import_module
from types import SimpleNamespace

import bpy
import numpy as np

import kit

gk = import_module(kit.MODULE + ".ui.graph_keys_draw")
chrome = import_module(kit.MODULE + ".ui.editor_chrome")
prefs_mod = import_module(kit.MODULE + ".preferences")


def _cube_with_keys(keys=((1, 0.0), (10, 5.0), (20, 0.0))):
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    ob = bpy.data.objects.new("pCube1", bpy.data.meshes.new("pCubeShape1"))
    bpy.context.scene.collection.objects.link(ob)
    for f, v in keys:
        ob.location = (v, 2 * v, 0.0)
        ob.rotation_euler.z = math.radians(10 * v)
        ob.keyframe_insert("location", frame=f)
        ob.keyframe_insert("rotation_euler", index=2, frame=f)
    for fc in kit.fcurves(ob):
        for kp in fc.keyframe_points:
            kp.select_control_point = False
    return ob


def _ctx(fcurves, normalized=False):
    space = SimpleNamespace(type='GRAPH_EDITOR', mode='FCURVES', use_normalization=normalized)
    return SimpleNamespace(visible_fcurves=list(fcurves), scene=bpy.context.scene, space_data=space,
                           preferences=bpy.context.preferences)


def _curve(ob, path, index):
    return kit.fcurves(ob).find(path, index=index)


def test_default_size_is_bigger_than_blenders():
    prefs = prefs_mod.get(bpy.context)
    blender = bpy.context.preferences.themes[0].graph_editor.vertex_size
    assert prefs.graph_key_size > blender, (prefs.graph_key_size, blender)
    assert gk.key_size(bpy.context) == prefs.graph_key_size
    r_in, r_out = gk.radii(bpy.context, prefs.graph_key_size)
    scale = bpy.context.preferences.system.ui_scale or 1.0
    assert r_in < blender * scale / 2 < r_out, (r_in, r_out)     # the rim overlaps Blender's own key


def test_handler_follows_enable():
    assert len(gk._handle) == 1
    kit.disable()
    try:
        assert not gk._handle
    finally:
        kit.enable()
    assert len(gk._handle) == 1


def test_key_points_split_by_selection():
    ob = _cube_with_keys()
    tx = _curve(ob, "location", 0)
    tx.keyframe_points[1].select_control_point = True
    curves = list(kit.fcurves(ob))
    unsel, sel = gk.key_points(_ctx(curves), _ctx(curves).space_data)
    assert sel.tolist() == [[10.0, 5.0]], sel
    assert len(unsel) == 3 * len(curves) - 1
    # rotation keys are drawn in degrees like the editor's curve
    rz = _curve(ob, "rotation_euler", 2)
    unsel, _sel = gk.key_points(_ctx([rz]), _ctx([rz]).space_data)
    if bpy.context.scene.unit_settings.system_rotation == 'DEGREES':
        assert np.allclose(unsel[:, 1], [0.0, 50.0, 0.0]), unsel


def test_key_points_normalized():
    ob = _cube_with_keys()
    ty = _curve(ob, "location", 1)
    unsel, _sel = gk.key_points(_ctx([ty], normalized=True), _ctx([ty], normalized=True).space_data)
    assert unsel[:, 1].min() >= -1.0 - 1e-6 and unsel[:, 1].max() <= 1.0 + 1e-6, unsel


def test_hidden_locked_and_unusable_curves_draw_no_keys():
    ob = _cube_with_keys()
    tx, ty, tz = (_curve(ob, "location", i) for i in range(3))
    tx.hide = True
    ty.lock = True
    tz.modifiers.new('ENVELOPE')
    unsel, sel = gk.key_points(_ctx([tx, ty, tz]), _ctx([tx, ty, tz]).space_data)
    assert len(unsel) == 0 and len(sel) == 0, (unsel, sel)
    tz.modifiers.remove(tz.modifiers[0])
    tz.modifiers.new('CYCLES')                       # Maya infinity: keys stay editable
    tz.select = False
    assert gk.draws_keys(tz, only_selected=False)
    assert not gk.draws_keys(tz, only_selected=True)     # Blender's "Only Show Selected F-Curve Keyframes"
    tz.select = True
    assert gk.draws_keys(tz, only_selected=True)


def test_rims_geometry():
    centres = np.array([[50.0, 50.0], [-100.0, 50.0], [60.0, 2000.0]])
    tris = gk.rims(centres, 3.0, 7.0, width=200, height=100)
    assert tris.shape == (gk.SEGMENTS * 6, 2), tris.shape          # only the key inside the region
    d = np.hypot(tris[:, 0] - 50.0, tris[:, 1] - 50.0)
    assert d.min() > 2.99 and d.max() < 7.01, (d.min(), d.max())
    assert gk.rims(np.zeros((0, 2)), 3.0, 7.0).shape == (0, 2)


def test_to_region_is_the_view_map():
    v2d = SimpleNamespace(region_to_view=lambda x, y: (x / 10.0 - 5.0, y / 20.0 + 1.0))
    region = SimpleNamespace(view2d=v2d, width=400, height=300)
    out = gk.to_region(region, np.array([[-5.0, 1.0], [35.0, 16.0], [0.0, 2.0]]))
    assert np.allclose(out, [[0.0, 0.0], [400.0, 300.0], [50.0, 20.0]]), out


def test_working_toolbar_buttons_have_their_own_icons():
    """Buttons that do different things never share an icon (the Auto tangent family all set Auto)."""
    for editor, icons in (("Graph Editor", chrome.GRAPH_ICONS), ("Dope Sheet", chrome.DOPE_ICONS)):
        seen = {}
        for it in icons:
            if not isinstance(it, tuple):
                continue
            key, icon, action, _tip = it
            seen.setdefault(icon, set()).add(repr(action) if action is not None else key)
        clashes = {icon: acts for icon, acts in seen.items() if len(acts) > 1}
        assert not clashes, (editor, clashes)


def _fold_ctx(width, region_type='FOOTER', scale=1.25):
    region = SimpleNamespace(type=region_type, width=width)
    system = SimpleNamespace(ui_scale=scale, pixel_size=1.0)
    return SimpleNamespace(region=region, preferences=SimpleNamespace(system=system))


def test_toolbar_folds_into_more_when_narrow():
    """A toolbar row too narrow for every button shows the leading groups in Maya's order; the rest go behind »."""
    groups = chrome.icon_groups("Graph Editor")
    assert len(groups) > 8 and groups[0][0][0] == "key_nearest_tool" and groups[-1][-1][0] == "open_time_editor"
    assert chrome.shown_groups(_fold_ctx(4000), "Graph Editor") == len(groups)
    n = chrome.shown_groups(_fold_ctx(950), "Graph Editor")
    assert 3 <= n < len(groups), n
    assert chrome.shown_groups(_fold_ctx(1400), "Graph Editor") > n
    # the menu-bar header (toolbar not on its own row) and the UV Editor keep every button
    assert chrome.shown_groups(_fold_ctx(950, 'HEADER'), "Graph Editor") == len(groups)
    assert chrome.shown_groups(_fold_ctx(300), "UV Editor") == len(chrome.icon_groups("UV Editor"))
    # every button is in exactly one group, in Maya's order
    flat = [it for g in groups for it in g]
    assert flat == [it for it in chrome.GRAPH_ICONS if it != "|"]


def test_more_menu_lists_the_hidden_buttons():
    class Rec:
        def __init__(self):
            self.log = []

        def operator(self, idname, text="", **kw):
            self.log.append(text)
            return SimpleNamespace()

        def menu(self, idname, text="", **kw):
            self.log.append(text)

        def prop(self, owner, attr, text="", **kw):
            self.log.append(text or attr)

        def __getattr__(self, name):
            return lambda *a, **k: SimpleNamespace()

    area = SimpleNamespace(as_pointer=lambda: 12345)
    space = SimpleNamespace(type='GRAPH_EDITOR', mode='FCURVES', use_normalization=False, use_auto_normalization=False)
    ctx = SimpleNamespace(area=area, space_data=space, scene=bpy.context.scene,
                          tool_settings=bpy.context.scene.tool_settings, preferences=bpy.context.preferences,
                          window_manager=bpy.context.window_manager)
    groups = chrome.icon_groups("Graph Editor")
    chrome._FIRST_HIDDEN[12345] = ("Graph Editor", len(groups) - 2)
    try:
        menu = SimpleNamespace(layout=Rec())
        chrome.ALLSET_MT_editor_more.draw(menu, ctx)
    finally:
        chrome._FIRST_HIDDEN.pop(12345, None)
    want = [it[3] for g in groups[-2:] for it in g if isinstance(it, tuple)]
    assert menu.layout.log == want, menu.layout.log


def _space(**kw):
    base = dict(type='GRAPH_EDITOR', mode='FCURVES', use_normalization=False, show_handles=True,
                use_only_selected_keyframe_handles=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_handle_points_follow_blenders_rules():
    ob = _cube_with_keys()
    tx = _curve(ob, "location", 0)
    for kp in tx.keyframe_points:
        kp.select_left_handle = kp.select_right_handle = False
    tx.keyframe_points[1].select_right_handle = True
    tx.keyframe_points[2].interpolation = 'LINEAR'          # last key: its right handle is not shown
    ctx = _ctx([tx])
    unsel, sel = gk.handle_points(ctx, _space())
    assert sel.tolist() == [list(tx.keyframe_points[1].handle_right)], sel
    # 3 keys x 2 sides, minus the last key's right side, minus the selected one
    assert len(unsel) == 4, unsel
    # a linear segment hides the handles on both of its ends
    tx.keyframe_points[0].interpolation = 'LINEAR'
    unsel, sel = gk.handle_points(ctx, _space())
    assert len(unsel) + len(sel) == 2, (unsel, sel)        # key 1 right, key 2 left
    # only around selected keys (Maya On Active Keys)
    tx.keyframe_points[0].interpolation = 'BEZIER'
    unsel, sel = gk.handle_points(ctx, _space(use_only_selected_keyframe_handles=True))
    assert len(unsel) == 1 and len(sel) == 1, (unsel, sel)        # key 2: left (unselected) + right (selected)
    # View > Show Handles off: none
    unsel, sel = gk.handle_points(ctx, _space(show_handles=False))
    assert not len(unsel) and not len(sel)


def test_handle_points_in_degrees_and_sizes():
    ob = _cube_with_keys()
    rz = _curve(ob, "rotation_euler", 2)
    unsel, sel = gk.handle_points(_ctx([rz]), _space())
    unsel = np.concatenate([unsel, sel])        # new keys come with selected handles
    if bpy.context.scene.unit_settings.system_rotation == 'DEGREES':
        ys = sorted(math.degrees(kp.handle_left.y) for kp in rz.keyframe_points)
        assert any(abs(y - ys[-1]) < 1e-6 for y in unsel[:, 1]), (unsel, ys)
    size = prefs_mod.get(bpy.context).graph_key_size
    h_in, h_out, h_dot = gk.handle_radii(bpy.context, size)
    k_in, k_out = gk.radii(bpy.context, size)
    curves = bpy.context.preferences.themes[0].common.curves
    blender = 1.4 * curves.handle_vertex_size / 2
    assert 0 < h_in < blender < h_out < k_out and h_dot > h_out, (h_in, h_out, h_dot, blender, k_out)
