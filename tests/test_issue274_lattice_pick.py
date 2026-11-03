"""Issue #274: on a lattice that a deformer bends, edit-mode points are clicked and boxed where they are drawn.

The kit picks by the evaluated (drawn) point positions projected to the view, with Maya's modifiers; on a lattice
drawn where its own points are, Blender's selection is left alone.
"""

from importlib import import_module
from types import SimpleNamespace

import bpy
import numpy as np
from mathutils import Matrix

import kit

lp = import_module(kit.MODULE + ".operators.lattice_pick")

W, H = 800, 600


def _fresh():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)


def _lattice(bend=True):
    _fresh()
    ob = bpy.data.objects.new("ffd1Lattice", bpy.data.lattices.new("ffd1LatticeShape"))
    bpy.context.scene.collection.objects.link(ob)
    ob.data.points_w = 4
    ob.location = (1.0, 2.0, 0.0)
    if bend:
        md = ob.modifiers.new("bend1", 'SIMPLE_DEFORM')
        md.deform_method = 'BEND'
        md.angle = 1.5
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    for p in ob.data.points:
        p.select = False
    return ob


def _persp():
    """A front orthographic view (looking along +Y): screen x = world x, screen y = world z, 100 px per unit."""
    s = 2.0 / W * 100, 2.0 / H * 100
    return Matrix(((s[0], 0, 0, 0), (0, 0, s[1], 0), (0, 0.001, 0, 0.5), (0, 0, 0, 1)))


def _ctx(ob, mode='EDIT_LATTICE'):
    region = SimpleNamespace(type='WINDOW', width=W, height=H)
    return SimpleNamespace(
        mode=mode, space_data=SimpleNamespace(type='VIEW_3D'), region=region,
        region_data=SimpleNamespace(perspective_matrix=_persp()), objects_in_mode=[ob],
        evaluated_depsgraph_get=bpy.context.evaluated_depsgraph_get, screen=None,
        preferences=SimpleNamespace(system=SimpleNamespace(pixel_size=1.0)))


def _event(x, y, shift=False, ctrl=False):
    return SimpleNamespace(mouse_region_x=x, mouse_region_y=y, shift=shift, ctrl=ctrl)


def _screen_of(ctx, ob, i, drawn=True):
    (_o, d, o), = lp.lattices(ctx)
    xy, _front = lp.project((d if drawn else o)[i:i + 1], np.asarray(_persp()), W, H)
    return xy[0]


def _selected(ob):
    return [i for i, p in enumerate(ob.data.points) if p.select]


def test_pure_rules():
    xy = np.array([[10.0, 10.0], [50.0, 10.0], [100.0, 100.0]])
    front = np.array([True, True, False])
    assert lp.nearest(xy, front, (48, 12), 75) == 1
    assert lp.nearest(xy, front, (99, 99), 5) is None          # behind the view
    assert lp.nearest(xy, front, (300, 300), 75) is None
    box = [(0, 0), (60, 0), (60, 20), (0, 20)]
    assert list(lp.inside(xy, [True] * 3, box)) == [True, True, False]
    lasso = [(0, 0), (30, 0), (30, 30), (0, 30), (0, 20)]
    assert list(lp.inside(xy, [True] * 3, lasso)) == [True, False, False]
    b, h = [True, True, False, False], [True, False, True, False]
    assert list(lp.combine(b, h, 'SET')) == h
    assert list(lp.combine(b, h, 'ADD')) == [True, True, True, False]
    assert list(lp.combine(b, h, 'SUB')) == [False, True, False, False]
    assert list(lp.combine(b, h, 'XOR')) == [False, True, True, False]
    assert list(lp.combine(b, h, 'AND')) == [True, False, False, False]
    assert [lp.click_mode(s, c) for s, c in ((0, 0), (1, 0), (0, 1), (1, 1))] == ['SET', 'XOR', 'SUB', 'ADD']


def test_drawn_points_are_the_deformed_ones():
    ob = _lattice()
    (o, drawn, own), = lp.lattices(_ctx(ob))
    assert o == ob and drawn.shape == own.shape == (16, 3)
    assert lp.deformed([(o, drawn, own)])
    assert abs(own[0][0] - 0.5) < 1e-6 and abs(own[0][1] - 1.5) < 1e-6      # world: location + (-0.5, -0.5, -0.5)
    plain = _lattice(bend=False)
    assert not lp.deformed(lp.lattices(_ctx(plain)))


def test_click_picks_the_drawn_point_with_maya_modifiers():
    ob = _lattice()
    ctx = _ctx(ob)
    # a point whose drawn spot is far from its own spot
    (_o, d, o), = lp.lattices(ctx)
    i = int(np.argmax(np.abs(d[:, 2] - o[:, 2])))
    x, y = _screen_of(ctx, ob, i)
    assert lp.click(ctx, _event(x, y))
    picked = _selected(ob)
    assert len(picked) == 1
    xs, ys = _screen_of(ctx, ob, picked[0])
    assert abs(xs - x) < 1e-3 and abs(ys - y) < 1e-3, "the point drawn under the click"
    first = picked[0]
    # Shift toggles: another drawn point is added, Shift on it again removes it
    j = next(k for k in range(16) if np.hypot(*(_screen_of(ctx, ob, k) - (x, y))) > 30)
    xj, yj = _screen_of(ctx, ob, j)
    lp.click(ctx, _event(xj, yj, shift=True))
    assert set(_selected(ob)) == {first, j}
    lp.click(ctx, _event(xj, yj, shift=True))
    assert _selected(ob) == [first]
    # Ctrl+Shift adds, Ctrl removes
    lp.click(ctx, _event(xj, yj, shift=True, ctrl=True))
    lp.click(ctx, _event(xj, yj, shift=True, ctrl=True))
    assert set(_selected(ob)) == {first, j}
    lp.click(ctx, _event(x, y, ctrl=True))
    assert _selected(ob) == [j]
    # a plain click far from every point clears the selection
    assert lp.click(ctx, _event(-5000, -5000))
    assert _selected(ob) == []


def test_box_uses_drawn_points_and_the_drag_mode():
    ob = _lattice()
    ctx = _ctx(ob)
    (_o, d, o), = lp.lattices(ctx)
    xy, _f = lp.project(d, np.asarray(_persp()), W, H)
    own_xy, _f = lp.project(o, np.asarray(_persp()), W, H)
    i = int(np.argmax(np.abs(d[:, 2] - o[:, 2])))
    x, y = xy[i]
    box = [(x - 2, y - 2), (x + 2, y - 2), (x + 2, y + 2), (x - 2, y + 2)]
    want = {k for k in range(16) if abs(xy[k][0] - x) <= 2 and abs(xy[k][1] - y) <= 2}
    assert i in want
    assert not any(abs(own_xy[k][0] - x) <= 2 and abs(own_xy[k][1] - y) <= 2 for k in want), "own spots elsewhere"
    ob.data.points[0].select = True
    snap = {ob.name: np.array([p.select for p in ob.data.points])}
    for p in ob.data.points:         # whatever Blender's own box did is replaced
        p.select = True
    assert lp.apply_region(ctx, box, 'SET', snap)
    assert set(_selected(ob)) == want
    assert lp.apply_region(ctx, box, 'ADD', snap)
    assert set(_selected(ob)) == want | {0}


def test_blender_keeps_selection_of_an_undeformed_lattice():
    ob = _lattice(bend=False)
    ctx = _ctx(ob)
    assert not lp.click(ctx, _event(400, 300))
    assert not lp.apply_region(ctx, [(0, 0), (W, 0), (W, H), (0, H)], 'SET', {})
    assert _selected(ob) == []
    assert not lp.box_takes(ctx)
    assert lp.box_takes(_ctx(_lattice()))          # the kit draws the marquee on a bent lattice
    assert not lp.click(_ctx(_lattice(), mode='EDIT_MESH'), _event(400, 300))


def test_hooks_sit_in_the_first_place_click_and_drag_items():
    mp = import_module(kit.MODULE + ".keymap.maya_patches")
    added = {(km, idname) for km, idname, *_rest in mp.ADDED}
    assert ("3D View", "allset.select_priority") in added
    assert ("3D View Tool: Select Box (fallback)", "allset.select_through") in added
    assert "allset.select_priority" in mp.PASS_THROUGH_FIRST and "allset.select_through" in mp.PASS_THROUGH_FIRST
