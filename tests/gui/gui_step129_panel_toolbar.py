"""#10: every button of the Maya panel toolbar clicked twice with simulated mouse clicks in the Maya
Workflow Kit layout — state before -> click -> after -> click -> after.

The viewport looks through a camera (so the camera buttons are enabled) and a cube is selected (Isolate Select).
Toggles must change on the first click and come back on the second (Maya iconTextCheckBox); commands act; greyed
buttons change nothing. Value fields (exposure / gamma / view transform) are not clicked.

#52: runs at the session's UI scale (1.25 on a 125 % display; ``--ui-scale 0.8`` = 1.0, ``1.2`` = 1.5).
The groups that don't fit the header are in the Maya » overflow popover: the test opens it, sweeps it top to bottom
and clicks those buttons there (the popover is reopened before every click)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, button_under_mouse, check, ev, run, screenshot, setup, step, view3d, win, load_maya_layout  # noqa: E402

GUI_TIMEOUT = 480
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
# buttons: command / data path -> (x0, x1, y0, y1) window px; popover: the ones found in the » popover
C = {"buttons": {}, "popover": set(), "rows": []}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def header():
    area, _r = view3d()
    return area, next(r for r in area.regions if r.type == 'TOOL_HEADER')


def snapshot():
    area, _r = view3d()
    sp = area.spaces.active
    sh, ov = sp.shading, sp.overlay
    scene = bpy.context.scene
    cam = bpy.data.objects.get(C.get("cam", ""))
    vs = scene.view_settings
    tool = bpy.context.workspace.tools.from_space_view3d_mode('OBJECT', create=False)
    return {
        "shading": sh.type, "light": sh.light, "color": sh.color_type, "shadows": sh.show_shadows,
        "cavity": sh.show_cavity, "xray": sh.show_xray, "dof": sh.use_dof, "wire_on_shaded": ov.show_wireframes,
        "xray_bone": ov.show_xray_bone, "grid": mod("ui.maya_grid").visible(sp),
        "cam_locked": bool(cam and all(cam.lock_location) and all(cam.lock_rotation)),
        "film_gate": bool(cam and cam.data.show_sensor), "gate_mask": bool(cam and cam.data.show_passepartout),
        "safe": bool(cam and cam.data.show_safe_areas), "isolate": sp.local_view is not None,
        "exposure": round(vs.exposure, 3), "gamma": round(vs.gamma, 3), "cm": vs.view_transform,
        "selected": tuple(sorted(o.name for o in scene.objects if o.select_get())),
        "objects": len(scene.objects), "tool": tool.idname if tool else "",
        "camera_view": sp.region_3d.view_perspective,
    }


def diff(a, b):
    return {k: (a[k], b[k]) for k in a if a[k] != b[k]}


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CAMERA')
        C["cam"] = bpy.context.view_layer.objects.active.name
        bpy.ops.allset.panel_look_through(camera=C["cam"])
        bpy.ops.allset.create(kind='CUBE')
    C["cube"] = bpy.context.view_layer.objects.active.name
    vs = bpy.context.scene.view_settings
    vs.exposure, vs.gamma = 1.0, 1.4      # non-default, so the exposure / gamma icons have a value to switch
    for a in win().screen.areas:
        a.tag_redraw()


def _record(key, x, y):
    """Button extent relative to the tool header: the Maya strip rows settle a moment after the layout loads and
    move the viewport header down (the clicks would hit the panel menu bar)."""
    _a, region = header()
    x, y = x - region.x, y - region.y
    x0, x1, y0, y1 = C["buttons"].get(key, (x, x, y, y))
    C["buttons"][key] = (min(x0, x), max(x1, x), min(y0, y), max(y1, y))


def sweep():
    """One probe per tick along the tool header's middle row, 4 px apart: every button's command and x range."""
    state = {}

    def look():
        area, region = header()
        if not state:
            state["x"] = region.x + 2
            state["y"] = region.y + region.height // 2
        else:
            path, cmd = button_under_mouse(area, region)
            key = cmd or path
            if key:
                _record(key, state["x"], state["y"])
            state["x"] += 4
            if state["x"] >= region.x + region.width - 2:
                return
        ev('MOUSEMOVE', 'NOTHING', x=state["x"], y=state["y"])
        import sim
        sim._steps.insert(0, look)
    return look


step(sweep())


def more_xy():
    """Centre of the » button (right end of the tool header, toolbar_fit.more_x)."""
    _a, region = header()
    fit = mod("ui.toolbar_fit")
    system = bpy.context.preferences.system
    x0, x1 = fit.more_x(region.width, system.ui_scale, system.pixel_size)
    return region.x + (x0 + x1) // 2, region.y + region.height // 2


@step
def s_bar():
    _a, region = header()
    pt, fit = mod("ui.panel_toolbar"), mod("ui.toolbar_fit")
    system = bpy.context.preferences.system
    C["shown"] = fit.fit(pt.fit_groups(), region.width, system.ui_scale, system.pixel_size)
    print("PT scale", system.ui_scale, "header", region.width, "groups shown", C["shown"], "of", len(pt.TOOLBAR) + 1)
    shown = sum(len(g) for g in pt.TOOLBAR[:C["shown"]]) + (3 if C["shown"] > len(pt.TOOLBAR) else 0)
    found = [k for k in C["buttons"] if "view_settings." not in k]
    check(f"UI scale {system.ui_scale:g}: the header shows {C['shown']} groups, every button of them found "
          f"({len(found)} of {shown})", len(found) == shown)
    _a, region = header()
    last = region.x + max((v[1] for v in C["buttons"].values()), default=0)
    if C["shown"] <= len(pt.TOOLBAR):
        check("the shown groups end left of the » button", last < more_xy()[0] - 4)
        ev('MOUSEMOVE', 'NOTHING', x=more_xy()[0], y=more_xy()[1])
    else:
        check("everything fits: no » button", last < region.x + region.width)


@step
def s_open_more():
    if C["shown"] <= len(mod("ui.panel_toolbar").TOOLBAR):
        x, y = more_xy()
        ev('LEFTMOUSE', 'PRESS', x=x, y=y)
        ev('LEFTMOUSE', 'RELEASE', x=x, y=y)


def sweep_popover():
    """Top to bottom under the » button, 4 px apart, until 60 px without a button after the last one: the
    popover's buttons (looked up through the header's open popover button). Five columns per row (the popover
    isn't centred on the »): the colour management lines have the icon button on the left and the field on the right."""
    state = {}

    def look():
        if C["shown"] > len(mod("ui.panel_toolbar").TOOLBAR):
            return
        area, region = header()
        cols = [more_xy()[0] + round(k * bpy.context.preferences.system.ui_scale) for k in (-100, -50, 0, 50, 100)]
        if not state:
            state["col"] = 0
            state["y"] = region.y - 4
            state["last"] = state["y"]
            if SHOTS:
                screenshot(os.path.join(SHOTS, f"gui_step132_more_{bpy.context.preferences.system.ui_scale:g}.png"))
        else:
            path, cmd = button_under_mouse(area, region)
            key = cmd or path
            if key and "panel_toolbar_more" not in key:
                _record(key, cols[state["col"]], state["y"])
                C["popover"].add(key)
                state["last"] = state["y"]
            state["col"] = (state["col"] + 1) % len(cols)
            if state["col"] == 0:
                state["y"] -= 4
            if state["y"] < 4 or state["last"] - state["y"] > 60:
                return
        ev('MOUSEMOVE', 'NOTHING', x=cols[state["col"]], y=state["y"])
        import sim
        sim._steps.insert(0, look)
    return look


step(sweep_popover())


@step
def s_found():
    if SHOTS:      # the open popover a moment later (screenshot shows the previous frame)
        screenshot(os.path.join(SHOTS, f"gui_step132_more_{bpy.context.preferences.system.ui_scale:g}_b.png"))
    ev('ESC', 'PRESS')
    ev('ESC', 'RELEASE')
    names = list(C["buttons"])
    print("PT buttons", len(names))
    for k, v in C["buttons"].items():
        print("PT", "pop" if k in C["popover"] else "bar", v, k)
    pt = mod("ui.panel_toolbar")
    expected = sum(len(g) for g in pt.TOOLBAR)
    clickable = [k for k in names if "view_settings." not in k]
    fields = [k for k in names if "view_settings." in k]
    scale = bpy.context.preferences.system.ui_scale
    check(f"UI scale {scale:g}: every panel toolbar icon reachable in the bar or the » popover ({len(clickable)} "
          f"buttons, {expected} icons + 3 colour management icons; {len(C['popover'])} in the popover)",
          len(clickable) == expected + 3)
    check(f"UI scale {scale:g}: exposure, gamma and view transform fields reachable ({fields})", len(fields) == 3)
    C["queue"] = clickable
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"gui_step129_toolbar_{scale:g}.png"))


def label_of(cmd):
    pt = mod("ui.panel_toolbar")
    for group in pt.TOOLBAR:
        for _g, kind, data, label in group:
            if kind == "set" and f"key='{data}'" in cmd:
                return label
            if kind == "prop" and cmd.endswith(f"{data[0] if data[0] != 'space' else ''}.{data[1]}".lstrip(".")):
                return label
            if kind == "run" and f'"{data[0]}"' in cmd:
                return label
            if kind == "grey" and f"Panel toolbar/{label}" in cmd:
                return label
    for key, label in (("EXPOSURE", "Exposure icon"), ("GAMMA", "Gamma icon"), ("CM_ENABLE", "Colour management")):
        if f"key='{key}'" in cmd:
            return label
    return cmd


def kind_of(cmd):
    if "menu_unavailable" in cmd:
        return "grey"
    if "SELECT_CAMERA" in cmd or "panel_run" in cmd:
        return "command"
    return "toggle"


def click_steps():
    """hover, [open the popover], click, mid, [open the popover], click, end — per button."""
    def in_pop():
        return C["queue"] and C["queue"][0] in C["popover"]

    def close():          # a popover left open by the last click (ESC goes to it; no-op in the viewport)
        if in_pop():
            ev('ESC', 'PRESS')
            ev('ESC', 'RELEASE')

    def to_more():
        if in_pop():
            ev('MOUSEMOVE', 'NOTHING', x=more_xy()[0], y=more_xy()[1])

    def open_more():
        if in_pop():
            x, y = more_xy()
            ev('LEFTMOUSE', 'PRESS', x=x, y=y)
            ev('LEFTMOUSE', 'RELEASE', x=x, y=y)

    def hover():
        if not C["queue"]:
            return
        x0, x1, y0, y1 = C["buttons"][C["queue"][0]]
        _a, region = header()
        C["xy"] = (region.x + (x0 + x1) // 2, region.y + (y0 + y1) // 2)
        ev('MOUSEMOVE', 'NOTHING', x=C["xy"][0], y=C["xy"][1])

    def click():
        if C["queue"]:
            ev('LEFTMOUSE', 'PRESS', x=C["xy"][0], y=C["xy"][1])
            ev('LEFTMOUSE', 'RELEASE', x=C["xy"][0], y=C["xy"][1])

    def mid():
        if C["queue"]:
            C["s1"] = snapshot()
            ev('MOUSEMOVE', 'NOTHING', x=C["xy"][0] + 1, y=C["xy"][1])

    def end():
        if not C["queue"]:
            return
        close()
        cmd = C["queue"].pop(0)
        s0, s1, s2 = C.pop("s0"), C["s1"], snapshot()
        C["rows"].append((label_of(cmd), kind_of(cmd), cmd, diff(s0, s1), diff(s1, s2), diff(s0, s2)))
        if "SELECT_CAMERA" in cmd or "wm.tool_set_by_id" in cmd:   # put the cube selection / Move tool back
            scene = bpy.context.scene
            for ob in scene.objects:
                ob.select_set(ob.name == C["cube"])
            bpy.context.view_layer.objects.active = scene.objects[C["cube"]]
            area, region = view3d()
            with bpy.context.temp_override(window=win(), area=area, region=region):
                bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
        import sim
        if C["queue"]:
            for f in reversed(seq):
                sim._steps.insert(0, f)

    def snap0():
        if C["queue"]:
            C["s0"] = snapshot()

    seq = (close, to_more, open_more, snap0, hover, click, mid, close, to_more, open_more, hover, click, end)
    return seq


for _f in click_steps():
    step(_f)


@step
def s_table():
    print("TABLE | Button | kind | 1st click | 2nd click | net |")
    for label, kind, cmd, d1, d2, d0 in C["rows"]:
        where = "popover" if cmd in C["popover"] else "bar"
        print(f"TABLE | {label} ({where}) | {kind} | {d1} | {d2} | {d0} |")
        if kind == "toggle":
            check(f"toolbar {label} ({where}): click turns it on, click again gives the start back ({d1} / {d0})",
                  d1 and not d0)
        elif kind == "grey":
            check(f"toolbar {label} ({where}): greyed button changes nothing ({d1})", not d1 and not d0)
        else:
            check(f"toolbar {label} ({where}): command acts ({d1} {d2})", d1 or d2)


run(interval=0.12)
