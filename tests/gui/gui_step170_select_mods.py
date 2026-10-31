"""In a real UI: Maya selection modifiers in the Graph Editor (Maya: a click on a selected key keeps the
selection, Ctrl+Shift+click only adds, Shift+marquee toggles, Ctrl+marquee deselects) and the Outliner (Shift+click =
range, Ctrl+click = toggle); screenshots (ALLSET_GUI_SHOTS)."""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
KEYS = {"ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT"}
FRAMES = ((1, 0.0), (10, 5.0), (20, 0.0))


def area():
    return C["area"]


def region():
    return next(r for r in area().regions if r.type == 'WINDOW')


def fcurve():
    ob = bpy.data.objects["Cube"]
    return ob.animation_data.action.layers[0].strips[0].channelbags[0].fcurves[0]


def keys():
    return [round(k.co.x) for k in fcurve().keyframe_points if k.select_control_point]


def set_keys(frames):
    for k in fcurve().keyframe_points:
        on = round(k.co.x) in frames
        k.select_control_point = on
        k.select_left_handle = k.select_right_handle = False
    area().tag_redraw()


def at(frame, value):
    def xy():
        r = region()
        x, y = r.view2d.view_to_region(frame, value, clip=False)
        return r.x + int(x), r.y + int(y)
    return xy


def corner(frame, key_value, dy):
    """A box corner beside a key: ``dy`` px above (+) / below (-) it, kept inside the region."""
    def xy():
        r = region()
        x, y = r.view2d.view_to_region(frame, key_value, clip=False)
        y = min(max(y + dy, 6), r.height - 6)
        x = min(max(x, 6), r.width - 6)
        return r.x + int(x), r.y + int(y)
    return xy


def wait(n=12):
    for _ in range(n):            # a second press within the double-click time is a DOUBLE_CLICK (no CLICK)
        step(lambda: None)


def click(xy, *mods):
    wait()

    def s1():
        ev('MOUSEMOVE', 'NOTHING', x=xy()[0], y=xy()[1])
        for m in mods:
            ev(KEYS[m], 'PRESS', x=xy()[0], y=xy()[1])

    def s3():
        for m in mods:
            ev(KEYS[m], 'RELEASE', x=xy()[0], y=xy()[1])

    def s2():
        # modifiers ride on the mouse events (separate simulated key presses stop CLICK / CLICK_DRAG)
        x, y = xy()
        kw = {m: True for m in mods}
        ev('LEFTMOUSE', 'PRESS', x=x, y=y, **kw)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y, **kw)
    step(s1)
    step(s2)
    step(s3)


def box(a, b, *mods):
    wait()
    kw = {m: True for m in mods}

    def s1():
        ev('MOUSEMOVE', 'NOTHING', x=a()[0], y=a()[1])

    def s_hold():                  # the held keys one tick before the press (gui_manual_sweep.drag)
        for m in mods:
            ev(KEYS[m], 'PRESS', x=a()[0], y=a()[1])

    def s2():
        ev('LEFTMOUSE', 'PRESS', x=a()[0], y=a()[1], **kw)

    def mv(f):
        def s():
            x0, y0 = a()
            x1, y1 = b()
            ev('MOUSEMOVE', 'NOTHING', x=int(x0 + (x1 - x0) * f), y=int(y0 + (y1 - y0) * f), **kw)
        return s

    def s3():
        ev('LEFTMOUSE', 'RELEASE', x=b()[0], y=b()[1], **kw)
        for m in mods:
            ev(KEYS[m], 'RELEASE', x=b()[0], y=b()[1])

    def s4():
        pass

    def dbg(tag):
        def s():
            r = region()
            print("DBGBOX", tag, mods, a(), b(), "region", r.x, r.y, r.width, r.height, "keys", keys(),
                  [m.bl_idname for m in win().modal_operators])
            if SHOTS:
                screenshot(os.path.join(SHOTS, f"dbg_box_{'_'.join(mods)}_{tag}.png"))
        return s
    for s in (s1, dbg("hover"), s_hold, s2, mv(0.3), mv(0.7), dbg("mid"), mv(1.0), dbg("end"), s3, s4, dbg("after"), s4):
        step(s)


@step
def s_setup():
    setup()
    ob = bpy.data.objects["Cube"]
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    for f, v in FRAMES:
        ob.location.x = v
        ob.keyframe_insert("location", index=0, frame=f)
    a, _r = view3d()
    C["area"] = a
    a.ui_type = 'FCURVES'


@step
def s_debug():
    for kcname in ("addon", "user", "active"):
        kc = getattr(bpy.context.window_manager.keyconfigs, kcname)
        km = kc.keymaps.get("Graph Editor")
        if km is None:
            print("DBG", kcname, "no Graph Editor"); continue
        rows = [(k.idname, k.type, k.value, k.shift, k.ctrl, k.active) for k in km.keymap_items
                if k.type == 'LEFTMOUSE']
        print("DBG", kcname, rows[:14])


@step
def s_view():
    with bpy.context.temp_override(window=win(), area=area(), region=region()):
        bpy.ops.graph.view_all()
        for _ in range(3):                 # room around the keys: box corners start on empty space
            bpy.ops.view2d.zoom_out()
    set_keys(())


click(at(10, 5.0))


@step
def s_plain():
    check(f"click on key 10 selects it ({keys()})", keys() == [10])
    set_keys((1, 10))


click(at(10, 5.0))


@step
def s_keep():
    check(f"click on the selected key 10 keeps 1 + 10 (Maya) ({keys()})", keys() == [1, 10])


click(at(10, 5.0), "ctrl", "shift")


@step
def s_add():
    check(f"Ctrl+Shift+click on a selected key only adds: 1 + 10 stay ({keys()})", keys() == [1, 10])
    set_keys((1, 10))


# Boxes: Blender's event simulation copies no modifier into the window's event state, so a simulated drag's
# CLICK_DRAG never carries Shift / Ctrl (the plain select_box runs). The kit pipeline is driven directly in
# the Graph Editor region instead: allset.select_2d_box (what Shift+drag runs first) + Blender's box as SET.
def run_box(op_kwargs, editor_box=True):
    def s():
        r = region()
        x0, y0 = r.view2d.view_to_region(*op_kwargs["a"], clip=False)
        x1, y1 = r.view2d.view_to_region(*op_kwargs["b"], clip=False)
        with bpy.context.temp_override(window=win(), area=area(), region=r):
            if editor_box:
                bpy.ops.allset.select_2d_box('INVOKE_DEFAULT', editor='GRAPH')
            bpy.ops.graph.select_box('EXEC_DEFAULT', True, mode=op_kwargs["mode"], xmin=int(min(x0, x1)),
                                     xmax=int(max(x0, x1)), ymin=int(min(y0, y1)), ymax=int(max(y0, y1)),
                                     wait_for_input=False)
    step(s)
    wait(4)


run_box({"a": (9, 6.5), "b": (23, -1.0), "mode": 'SET'})


@step
def s_xor():
    check(f"Shift+marquee over 10 + 20 toggles them: 1 + 20 (Maya) ({keys()})", keys() == [1, 20])


run_box({"a": (18, 1.0), "b": (23, -1.0), "mode": 'SUB'}, editor_box=False)


@step
def s_sub():
    check(f"Ctrl+marquee over 20 deselects it: 1 ({keys()})", keys() == [1])
    set_keys((1, 10, 20))


run_box({"a": (9, 6.5), "b": (23, -1.0), "mode": 'SUB'}, editor_box=False)


@step
def s_sub_shot():
    check(f"Ctrl+marquee over 10 + 20 leaves key 1 ({keys()})", keys() == [1])
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step170_graph_ctrl_box.png"))


# --- Outliner ---------------------------------------------------------------------------------------------------------

@step
def s_outliner():
    for name in ("pA1", "pA2", "pA3", "pA4"):
        ob = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(ob)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    area().ui_type = 'OUTLINER'


@step
def s_rows():
    r = region()
    s = bpy.context.preferences.system.ui_scale
    C["row"] = round(20 * s)
    C["rows"] = {}
    C["probe"] = [r.y + r.height - int(C["row"] * (i + 0.5)) for i in range(16)]


def probe(i):
    def s_click():
        r = region()
        y = C["probe"][i]
        ev('MOUSEMOVE', 'NOTHING', x=r.x + int(r.width * 0.35), y=y)
        ev('LEFTMOUSE', 'PRESS', x=r.x + int(r.width * 0.35), y=y)
        ev('LEFTMOUSE', 'RELEASE', x=r.x + int(r.width * 0.35), y=y)

    def s_look():
        sel = [o.name for o in bpy.context.view_layer.objects if o.select_get()]
        if len(sel) == 1 and sel[0] not in C["rows"]:
            C["rows"][sel[0]] = C["probe"][i]
    step(s_click)
    step(s_look)


for _i in range(16):
    probe(_i)


def row(name):
    def xy():
        r = region()
        return r.x + int(r.width * 0.35), C["rows"].get(name, r.y)
    return xy


def selected():
    return sorted(o.name for o in bpy.context.view_layer.objects if o.select_get())


@step
def s_rows_found():
    check(f"Outliner rows found ({sorted(C['rows'])})", all(n in C["rows"] for n in ("pA1", "pA2", "pA3", "pA4")))


click(row("pA1"))
click(row("pA3"), "shift")


@step
def s_range():
    check(f"Shift+click = range pA1..pA3 (Maya Outliner) ({selected()})", selected() == ["pA1", "pA2", "pA3"])
    if SHOTS:
        screenshot(os.path.join(SHOTS, "gui_step170_outliner_range.png"))


def ctrl_click(xy):
    """Ctrl+click: the Outliner keymap item (extend, no range) at the hovered row (a simulated Ctrl CLICK carries no
    Ctrl, see above)."""
    wait()

    def s1():
        ev('MOUSEMOVE', 'NOTHING', x=xy()[0], y=xy()[1])

    def s2():
        with bpy.context.temp_override(window=win(), area=area(), region=region()):
            bpy.ops.allset.select_2d_click('INVOKE_DEFAULT', editor='OUTLINER', rule='TOGGLE')   # first in the keymap
            bpy.ops.outliner.item_activate('INVOKE_DEFAULT', extend=True, extend_range=False, deselect_all=True)
    step(s1)
    step(s2)
    wait(2)


ctrl_click(row("pA2"))


@step
def s_toggle():
    check(f"Ctrl+click toggles pA2 off ({selected()})", selected() == ["pA1", "pA3"])


ctrl_click(row("pA4"))


@step
def s_toggle_on():
    check(f"Ctrl+click toggles pA4 on ({selected()})", selected() == ["pA1", "pA3", "pA4"])

def real_ctrl_click(xy):
    """A real Ctrl+click: the Ctrl key event carries the modifier into the window state, then the click."""
    wait()

    def s1():
        ev('MOUSEMOVE', 'NOTHING', x=xy()[0], y=xy()[1])
        ev('LEFT_CTRL', 'PRESS', x=xy()[0], y=xy()[1], ctrl=True)

    def s2():
        x, y = xy()
        ev('LEFTMOUSE', 'PRESS', x=x, y=y, ctrl=True)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y, ctrl=True)

    def s3():
        ev('LEFT_CTRL', 'RELEASE', x=xy()[0], y=xy()[1])
    step(s1)
    step(s2)
    step(s3)
    wait(2)


real_ctrl_click(row("pA1"))


@step
def s_real_ctrl_off():
    check(f"real Ctrl+click toggles pA1 off ({selected()})", selected() == ["pA3", "pA4"])


real_ctrl_click(row("pA2"))


@step
def s_real_ctrl_on():
    check(f"real Ctrl+click adds pA2 ({selected()})", selected() == ["pA2", "pA3", "pA4"])


run()
