"""Maya curve drawing tools (operators/curve_draw.py) — click projection (persp ground / ortho view plane),
the point-list state machine (press / drag / release / Backspace / Enter rules), grid snap and that finishing calls the
curves_maya maker with the clicked points. GUI: tests/gui/gui_step156_curves.py."""

import math
import types
from importlib import import_module

import bpy
from mathutils import Matrix, Vector

import kit

cd = import_module(kit.MODULE + ".operators.curve_draw")
curves_maya = import_module(kit.MODULE + ".operators.curves_maya")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for c in list(bpy.data.curves):
        bpy.data.curves.remove(c)


def _view(eye, target, persp=True, w=800, h=600, lens_fov=math.radians(50), ortho_size=10.0):
    """A fake (region, rv3d) pair looking from ``eye`` at ``target`` (Z up)."""
    eye, target = Vector(eye), Vector(target)
    fwd = (target - eye).normalized()
    up = Vector((0, 0, 1)) if abs(fwd.z) < 0.999 else Vector((0, 1, 0))
    right = fwd.cross(up).normalized()
    up = right.cross(fwd)
    rot = Matrix((right, up, -fwd)).transposed().to_4x4()
    view = (Matrix.Translation(eye) @ rot).inverted()
    aspect = w / h
    n, f = 0.1, 1000.0
    if persp:
        t = 1.0 / math.tan(lens_fov / 2)
        proj = Matrix(((t / aspect, 0, 0, 0), (0, t, 0, 0), (0, 0, (f + n) / (n - f), 2 * f * n / (n - f)), (0, 0, -1, 0)))
    else:
        s = ortho_size / 2
        proj = Matrix(((1 / (s * aspect), 0, 0, 0), (0, 1 / s, 0, 0), (0, 0, -2 / (f - n), -(f + n) / (f - n)), (0, 0, 0, 1)))
    rv3d = types.SimpleNamespace(view_matrix=view, perspective_matrix=proj @ view, is_perspective=persp,
                                 view_perspective='PERSP' if persp else 'ORTHO')
    return types.SimpleNamespace(width=w, height=h), rv3d


def _screen(region, rv3d, p):
    v = rv3d.perspective_matrix @ Vector((*p, 1.0))
    return ((v.x / v.w + 1) * region.width / 2, (v.y / v.w + 1) * region.height / 2)


def test_persp_click_lands_on_ground():
    region, rv3d = _view((10, -10, 8), (0, 0, 0))
    for target in ((0, 0, 0), (3, 2, 0), (-4, 1.5, 0)):
        p = cd.plane_point(region, rv3d, _screen(region, rv3d, target))
        assert p.z == 0.0 and (p - Vector(target)).length < 2e-3, (tuple(p), target)
    # above the horizon: falls back to the view plane through the origin (no point behind the eye)
    p = cd.plane_point(region, rv3d, (400, 599))
    assert p.length < 1e3, tuple(p)


def test_ortho_click_lands_on_view_plane():
    # Blender front view (Maya front): looking along +Y, points on y = 0
    region, rv3d = _view((0, -50, 0), (0, 0, 0), persp=False)
    p = cd.plane_point(region, rv3d, _screen(region, rv3d, (2, 7, 3)))
    assert p.y == 0.0 and abs(p.x - 2) < 1e-4 and abs(p.z - 3) < 1e-4, tuple(p)
    # top view: z = 0
    region, rv3d = _view((0, 0, 50), (0, 0, 0), persp=False)
    p = cd.plane_point(region, rv3d, _screen(region, rv3d, (1.5, -2, 9)))
    assert p.z == 0.0 and abs(p.x - 1.5) < 1e-4 and abs(p.y + 2) < 1e-4, tuple(p)


def test_cv_state_machine():
    d = cd.Drawing(cd.CV, 3)
    assert cd.needed(cd.CV, 3) == 4 and cd.needed(cd.CV, 1) == 2 and cd.needed(cd.EP) == 2
    for i in range(3):
        assert d.press((i, 0, 0))
        d.drag((i, 1, 0))                    # drag moves the new point
        assert not d.release((i, 2, 0))      # CV curves never finish on a click
    assert [tuple(p) for p in d.points] == [(0, 2, 0), (1, 2, 0), (2, 2, 0)]
    assert not d.can_finish()                # Enter with 3 CVs: Maya keeps waiting for degree + 1
    d.press((3, 0, 0))
    d.release()
    assert d.can_finish()
    d.pop()                                  # Backspace
    assert len(d.points) == 3 and not d.can_finish()
    d.drag((9, 9, 9))                        # not dragging: no change
    assert tuple(d.points[-1]) == (2, 2, 0)


def test_ep_and_arcs_state_machine():
    d = cd.Drawing(cd.EP)
    d.press((0, 0, 0)); d.release()
    assert not d.can_finish()
    d.press((1, 0, 0)); d.release()
    assert d.can_finish()
    a = cd.Drawing(cd.ARC3)
    assert not (a.press((0, 0, 0)) and a.release())
    assert not (a.press((1, 1, 0)) and a.release())
    assert a.press((2, 0, 0)) and a.release((2.5, 0, 0))     # finishes on the third release
    assert not a.press((3, 3, 0)) and len(a.points) == 3
    b = cd.Drawing(cd.ARC2)
    b.press((0, 0, 0))
    assert not b.release()
    b.press((4, 0, 0))
    assert b.release()


def test_grid_snap():
    step = cd.grid_step(bpy.context.scene)
    assert abs(step - 1.0 * kit_unit()) < 1e-9, step     # default grid: 5 spacing / 5 divisions = 1 unit
    p = cd.snap_grid(Vector((1.4 * step, -2.6 * step, 0.0)), step)
    assert (p - Vector((step, -3 * step, 0.0))).length < 1e-9


def kit_unit():
    return import_module(kit.MODULE + ".operators.units").maya_unit(bpy.context.scene)


def test_make_calls_curves_maya_with_points():
    _clear()
    calls = []
    saved = {k: getattr(curves_maya, k) for k in ("make_cv_curve", "make_ep_curve", "make_arc3", "make_arc2")}

    def spy(name):
        def f(context, *args):
            calls.append((name, args))
            return saved[name](context, *args)
        return f

    try:
        for k in saved:
            setattr(curves_maya, k, spy(k))
        pts = [Vector((i, i * 0.5, 0)) for i in range(4)]
        ob = cd.make(bpy.context, cd.CV, pts, 3)
        assert calls[-1][0] == "make_cv_curve" and calls[-1][1][1] == 3
        assert [tuple(p) for p in calls[-1][1][0]] == [tuple(p) for p in pts]
        assert ob.name == "curve1" and ob.type == 'CURVE' and len(ob.data.splines) == 1, ob.name
        assert ob.data.name == "curveShape1", ob.data.name
        ob2 = cd.make(bpy.context, cd.EP, pts[:2], 3)
        assert calls[-1][0] == "make_ep_curve" and len(calls[-1][1][0]) == 2 and ob2.name == "curve2"
        cd.make(bpy.context, cd.ARC3, pts[:3])
        assert calls[-1][0] == "make_arc3" and [tuple(p) for p in calls[-1][1]] == [tuple(p) for p in pts[:3]]
        cd.make(bpy.context, cd.ARC2, pts[:2])
        assert calls[-1][0] == "make_arc2" and len(calls[-1][1]) == 2
        assert {o.name for o in bpy.data.objects} == {"curve1", "curve2", "curve3", "curve4"}
    finally:
        for k, v in saved.items():
            setattr(curves_maya, k, v)
        _clear()


def test_operators_registered_undo_only():
    for idname in ("cv_curve_tool", "ep_curve_tool", "arc3_tool", "arc2_tool"):
        cls = getattr(bpy.types, "ALLSET_OT_" + idname)
        assert cls.bl_options == {'UNDO'}, (idname, cls.bl_options)     # Maya has no redo panel
        assert hasattr(bpy.ops.allset, idname)
    # background INVOKE runs execute: without points nothing happens, no preview handler left
    assert bpy.ops.allset.ep_curve_tool('INVOKE_DEFAULT') == {'CANCELLED'}
    assert not cd._handles and cd.STATE["owner"] is None
    _clear()
    import json
    pts = [(0, 0, 0), (1, 2, 0), (3, 1, 0)]
    assert bpy.ops.allset.cv_curve_tool(points=json.dumps(pts)) == {'CANCELLED'}       # 3 < degree + 1
    assert bpy.ops.allset.cv_curve_tool(points=json.dumps(pts), degree=2) == {'FINISHED'}
    assert bpy.ops.allset.arc3_tool(points=json.dumps(pts)) == {'FINISHED'}
    names = sorted(o.name for o in bpy.data.objects)
    assert names == ["curve1", "curve2"], names
    _clear()
