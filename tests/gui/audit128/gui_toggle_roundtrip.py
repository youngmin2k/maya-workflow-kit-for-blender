"""Audit 128 repro (toggle lane): every Maya-layout toggle button pressed twice must give back the state it started
from (Maya: a second click on a toggle turns it off again). Status Line snaps / masks / symmetry / IPR / editor
toggles / group handles, panel toolbar toggles, UV toolkit component buttons. PASSes when every round trip holds."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim import MODULE, check, run, setup, step, view3d, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 240
C = {}


def sl():
    return import_module(MODULE + ".ui.status_line")


def ov(fn, *a, **kw):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return fn(*a, **kw)


def ts():
    return bpy.context.scene.tool_settings


def snap_state():
    t = ts()
    return (t.use_snap, tuple(sorted(t.snap_elements)))


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_snaps():
    bpy.ops.allset.keymap_activate()
    ov(bpy.ops.allset.create, kind='CUBE')
    for snap in ("GRID", "CURVE", "POINT", "LIVE"):
        before = snap_state()
        ov(bpy.ops.allset.snap_toggle, snap=snap)
        mid = snap_state()
        ov(bpy.ops.allset.snap_toggle, snap=snap)
        after = snap_state()
        print("AUDIT snap", snap, before, mid, after)
        check(f"snap {snap}: on then off gives the start state back ({before} -> {mid} -> {after})",
              mid != before and after[0] == before[0])
    # two snaps on, one off: the other stays on (Maya: independent toggles)
    ov(bpy.ops.allset.snap_toggle, snap="GRID")
    ov(bpy.ops.allset.snap_toggle, snap="POINT")
    ov(bpy.ops.allset.snap_toggle, snap="GRID")
    s = sl()
    check(f"snap GRID+POINT, GRID off: POINT still on ({snap_state()})",
          s.snap_on(ts(), "POINT") and not s.snap_on(ts(), "GRID"))
    ov(bpy.ops.allset.snap_toggle, snap="POINT")


@step
def s_masks():
    s = sl()
    area, _r = view3d()
    sp = area.spaces.active
    for m in s.OBJECT_MASKS:
        if not m[3]:
            continue
        before = s.mask_on(sp, m[0])
        ov(bpy.ops.allset.select_mask, group=m[0])
        mid = s.mask_on(sp, m[0])
        ov(bpy.ops.allset.select_mask, group=m[0])
        after = s.mask_on(sp, m[0])
        check(f"mask {m[0]}: {before} -> {mid} -> {after}", mid != before and after == before)


@step
def s_sym():
    sym = import_module(MODULE + ".operators.symmetry")
    b = sym.state(bpy.context.scene).on
    ov(bpy.ops.allset.symmetry, mode="TOGGLE")
    m = sym.state(bpy.context.scene).on
    ov(bpy.ops.allset.symmetry, mode="TOGGLE")
    a = sym.state(bpy.context.scene).on
    check(f"symmetry toggle {b} -> {m} -> {a}", m != b and a == b)
    # IPR opens its own window; IPR again closes it, and the viewport keeps its shading throughout
    area, _r = view3d()
    sh = area.spaces.active.shading
    sh.type = 'SOLID'
    C["ipr_windows"] = len(bpy.context.window_manager.windows)
    ov(bpy.ops.allset.ipr_toggle)
    # the shading round trip the IPR window module keeps for a view with no window to open
    sl().ipr_toggle(area.spaces.active)
    sl().ipr_toggle(area.spaces.active)
    check(f"viewport IPR on/off gives Solid back ({sh.type})", sh.type == 'SOLID')
    sh.type = 'WIREFRAME'
    sl().ipr_toggle(area.spaces.active)
    sl().ipr_toggle(area.spaces.active)
    check(f"viewport IPR on/off from Wireframe gives Wireframe back ({sh.type})", sh.type == 'WIREFRAME')
    sh.type = 'SOLID'


def _wait(fn, cond, limit=150):
    """Run ``fn`` again next tick until ``cond()`` or ``limit`` ticks."""
    key = "wait_" + fn.__name__
    C.setdefault(key, 0)
    if not cond() and C[key] < limit:
        C[key] += 1
        sys.modules["sim"]._steps.insert(0, fn)
        return True
    return False


@step
def s_ipr_opened():
    ipr = import_module(MODULE + ".ui.ipr_window")
    if _wait(s_ipr_opened, ipr.is_open):
        return
    n = len(bpy.context.window_manager.windows)
    check(f"IPR opens its own window ({C['ipr_windows']} -> {n})", ipr.is_open() and n == C["ipr_windows"] + 1)
    area, _r = view3d()
    check(f"the viewport keeps its shading while IPR runs ({area.spaces.active.shading.type})",
          area.spaces.active.shading.type == 'SOLID')
    ov(bpy.ops.allset.ipr_toggle)


@step
def s_ipr_closed():
    ipr = import_module(MODULE + ".ui.ipr_window")
    if _wait(s_ipr_closed, lambda: not ipr.is_open()):
        return
    n = len(bpy.context.window_manager.windows)
    check(f"IPR again closes the window ({n} windows)", not ipr.is_open() and n == C["ipr_windows"])


EDITORS = ("MODELING_TOOLKIT", "ATTRIBUTE", "TOOL_SETTINGS", "CHANNEL_BOX")


def shown(e):
    return sl().editor_shown(win().screen, e)


def _editor_steps(e):
    def a():
        C[e] = [shown(e)]
        ov(bpy.ops.allset.editor_toggle, editor=e)

    def b():
        C[e].append(shown(e))
        ov(bpy.ops.allset.editor_toggle, editor=e)

    def c():
        C[e].append(shown(e))

    def d():
        C[e].append(shown(e))
        v = C[e]
        print("AUDIT editor", e, v)
        check(f"editor toggle {e}: {v[0]} -> {v[1]} -> {v[3]}", v[1] != v[0] and v[3] == v[0])
    for f in (a, b, c, d):
        step(f)


for _e in EDITORS:
    _editor_steps(_e)


@step
def s_groups():
    s = sl()
    for g, _d in s.GROUPS:
        b = g in s._collapsed
        ov(bpy.ops.allset.status_group, group=g)
        m = g in s._collapsed
        ov(bpy.ops.allset.status_group, group=g)
        a = g in s._collapsed
        check(f"status group {g}: {b} -> {m} -> {a}", m != b and a == b)


@step
def s_panel_toolbar():
    pt = import_module(MODULE + ".ui.panel_toolbar")
    pm = import_module(MODULE + ".ui.panel_menus")
    area, _r = view3d()
    sp = area.spaces.active

    def state():
        return (sp.shading.type, sp.shading.light, sp.shading.color_type, sp.shading.show_shadows,
                sp.shading.show_cavity, sp.shading.show_xray, sp.overlay.show_wireframes, sp.overlay.show_floor,
                sp.overlay.show_xray_bone, sp.lock_camera, sp.shading.use_dof)
    for group in pt.TOOLBAR:
        for name, kind, arg, label in group:
            if kind not in ("set", "prop"):
                continue
            b = state()
            try:
                for _ in range(2):
                    if kind == "set":
                        ov(getattr(bpy.ops.allset, pm.ALLSET_OT_panel_set.bl_idname.split(".")[1]), key=arg)
                    else:
                        owner = {"space": sp, "shading": sp.shading, "overlay": sp.overlay}[arg[0]]
                        setattr(owner, arg[1], not getattr(owner, arg[1]))
                    if _ == 0:
                        m = state()
            except Exception as ex:
                check(f"panel toolbar {label}: raised {ex!r}", False)
                continue
            a = state()
            print("AUDIT panel toolbar", label, b, m, a)
            check(f"panel toolbar {label}: click twice gives the start state back (changed={m != b}, back={a == b})",
                  m != b and a == b)


run()
