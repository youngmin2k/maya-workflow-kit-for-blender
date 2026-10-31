"""In a real UI (Maya Workflow Kit layout): EP Curve Tool -> 4 clicks in the persp view (ground) -> Enter
-> curve1; CV Curve Tool -> 4 clicks + Enter -> curve2 (an Enter after 3 CVs keeps waiting); Three Point Circular Arc ->
3 clicks (finishes on the last) -> curve3. Every point on z = 0, curve ends = the first / last click."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def cd():
    return import_module(MODULE + ".operators.curve_draw")


def main_view():
    toolbox = import_module(MODULE + ".ui.toolbox")
    areas = [a for a in win().screen.areas if a.type == 'VIEW_3D' and not toolbox.is_toolbox(a.spaces.active)]
    area = max(areas, key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def running(idname):
    return idname in [op.bl_idname for op in win().modal_operators]


def start(op, clicks):
    area, region = main_view()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        getattr(bpy.ops.allset, op)('INVOKE_DEFAULT')
    C["clicks"] = [(region.x + int(region.width * f), region.y + int(region.height * g)) for f, g in clicks]
    C["i"] = 0


def hover():
    x, y = C["clicks"][C["i"]]
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)


def press():
    x, y = C["clicks"][C["i"]]
    ev('LEFTMOUSE', 'PRESS', x=x, y=y)


def release():
    x, y = C["clicks"][C["i"]]
    ev('LEFTMOUSE', 'RELEASE', x=x, y=y)
    C["i"] += 1


def clicks(n):
    for _ in range(n):
        step(hover)
        step(press)
        step(release)


def check_curve(name, kind, n, count_ok):
    ob = bpy.data.objects.get(name)
    check(f"{kind}: {name} exists ({sorted(o.name for o in bpy.data.objects if o.type == 'CURVE')})",
          ob is not None and ob.type == 'CURVE')
    if ob is None or ob.type != 'CURVE':
        return
    splines = ob.data.splines
    check(f"{kind}: one spline ({len(splines)})", len(splines) == 1)
    last = cd().LAST
    pts = last["points"]
    check(f"{kind}: {n} clicked points recorded ({last['kind']}, {len(pts)})", last["kind"] == kind and len(pts) == n)
    check(f"{kind}: clicks land on the ground (z max {max(abs(p.z) for p in pts):.2e})",
          all(abs(p.z) < 1e-6 for p in pts))
    sp = splines[0]
    cos = [ob.matrix_world @ p.co.xyz for p in sp.points] if sp.type != 'BEZIER' else \
        [ob.matrix_world @ p.co for p in sp.bezier_points]
    check(f"{kind}: spline point count fits ({len(cos)})", count_ok(len(cos)))
    check(f"{kind}: curve points on z = 0 (max {max(abs(c.z) for c in cos):.2e})", all(abs(c.z) < 1e-5 for c in cos))
    ends = (cos[0] - pts[0]).length, (cos[-1] - pts[-1]).length
    check(f"{kind}: curve ends = first / last click ({ends[0]:.2e}, {ends[1]:.2e})", max(ends) < 1e-4)
    check(f"{kind}: {name} is the selected lead", bpy.context.view_layer.objects.active == ob and ob.select_get())


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_ep_start():
    for ob in list(bpy.data.objects):
        ob.select_set(False)
    start("ep_curve_tool", ((0.30, 0.30), (0.42, 0.18), (0.56, 0.28), (0.70, 0.20)))
    check("EP Curve Tool runs as a window modal", running("ALLSET_OT_ep_curve_tool"))


clicks(4)


@step
def s_ep_preview():
    for a in win().screen.areas:
        a.tag_redraw()
    check(f"EP preview holds 4 points ({len(cd().STATE['points'])})", len(cd().STATE["points"]) == 4)
    check("EP preview draw handler is on", bool(cd()._handles))


@step
def s_ep_shot():
    shot("gui_step156_ep_drawing.png")
    tap('RET')


@step
def s_ep_done():
    check("Enter ends the EP Curve Tool", not running("ALLSET_OT_ep_curve_tool"))
    check("preview handler removed", not cd()._handles)
    check_curve("curve1", "EP", 4, lambda k: k in (4, 6))    # stub: CVs = EPs; Maya cubic EP: n + 2 CVs
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_ep_final_shot():
    shot("gui_step156_ep_curve.png")
    start("cv_curve_tool", ((0.25, 0.22), (0.38, 0.32), (0.52, 0.18), (0.66, 0.30)))
    check("CV Curve Tool runs", running("ALLSET_OT_cv_curve_tool"))


clicks(3)


@step
def s_cv_early_enter():
    tap('RET')


@step
def s_cv_waits():
    check("Enter with 3 CVs: the CV Curve Tool keeps waiting (degree 3 needs 4)",
          running("ALLSET_OT_cv_curve_tool") and bpy.data.objects.get("curve2") is None)


clicks(1)


@step
def s_cv_enter():
    shot("gui_step156_cv_drawing.png")
    tap('RET')


@step
def s_cv_done():
    check("Enter ends the CV Curve Tool", not running("ALLSET_OT_cv_curve_tool"))
    check_curve("curve2", "CV", 4, lambda k: k == 4)
    start("arc3_tool", ((0.35, 0.12), (0.50, 0.30), (0.65, 0.12)))
    check("Three Point Circular Arc runs", running("ALLSET_OT_arc3_tool"))


clicks(3)


@step
def s_arc_done():
    check("the third click ends the Three Point Circular Arc", not running("ALLSET_OT_arc3_tool"))
    check_curve("curve3", "ARC3", 3, lambda k: k >= 3)
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_arc_shot():
    shot("gui_step156_arc3.png")
    start("ep_curve_tool", ((0.4, 0.3), (0.5, 0.25)))


clicks(2)


@step
def s_backspace():
    tap('BACK_SPACE')


@step
def s_esc():
    n = len(cd().STATE["points"])
    check(f"Backspace removes the last point ({n})", n == 1)
    tap('ESC')


@step
def s_cancelled():
    check("Esc stops the tool without a curve", not running("ALLSET_OT_ep_curve_tool")
          and bpy.data.objects.get("curve4") is None and not cd()._handles)


run()
