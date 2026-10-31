"""G1 / G2 in the Maya Workflow Kit layout: Edit > Group prints Maya's result in the
Command Line result field and puts no Blender report banner in the status bar (step-154 dogfood 05: "Grouped 2
object(s) into group1" with Blender's info icon); the RMB list near the window bottom stays one column (Maya) instead
of wrapping into three. Shots with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, scale, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def main_view():
    return mod("ui.status_line").main_view3d(win().screen)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()
    mod("ui.status_line").redraw_top_bars()


def shot(name):
    path = os.path.join(SHOTS or bpy.app.tempdir, f"gui_step161_{name}_{scale():.2f}.png".replace(".", "", 1))
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def help_line(px):
    """The status bar's left half (Help Line, where Blender's report banner shows)."""
    h = int(26 * scale())              # the status bar row
    return px[2:h - 2, : px.shape[1] // 2 - 40]


def result_part(px):
    """The status bar's right part (Command Line result field and buttons)."""
    h = int(26 * scale())
    return px[2:h - 2, int(px.shape[1] * 0.72):]


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.allset.create(kind='CUBE')
    for o in bpy.context.scene.objects:
        o.select_set(o.type == 'MESH')
    mod("command_line")._result["text"] = ""
    redraw()


step(redraw)


@step
def s_before():
    px = shot("before_group")
    C["before"] = help_line(px)
    C["result_before"] = result_part(px)
    area, region = main_view()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        mod("marking.modal").run_action(bpy.context, ("allset.group", {}), path="Edit/Group")
    redraw()


step(redraw)


@step
def s_after():
    px = shot("after_group")
    after = help_line(px)
    text = mod("command_line")._result["text"]
    grp = bpy.context.view_layer.objects.active
    check(f"G1 Edit > Group: Maya's result in the Command Line result field ({text!r})",
          grp is not None and text == f"Result: {grp.name}")
    diff = float(np.abs(after - C["before"]).max()) if after.shape == C["before"].shape else 1.0
    check(f"G1 no Blender report banner in the Help Line (max change {diff:.3f})", diff < 0.05)
    changed = float((np.abs(result_part(px) - C["result_before"]).max(axis=-1) > 0.2).mean())
    check(f"G1 the result text is drawn in the status bar's result field, inside the window ({changed:.3f} changed)",
          changed > 0.005)


# --- G2: RMB list low in the window --------------------------------------------------------------------------------

@step
def s_low():
    bpy.ops.object.select_all(action='DESELECT')
    _area, region = main_view()
    ob = bpy.data.objects["pCube1"]
    p = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation)
    rv3d = region.data
    # pan so pCube1 sits 60 px above the view's bottom
    from bpy_extras.view3d_utils import region_2d_to_location_3d
    target = region_2d_to_location_3d(region, rv3d, (p.x, 60), ob.matrix_world.translation)
    rv3d.view_location = rv3d.view_location + (ob.matrix_world.translation - target)
    redraw()


step(redraw)


@step
def s_rmb_press():
    _area, region = main_view()
    ob = bpy.data.objects["pCube1"]
    p = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation)
    x, y = region.x + int(p.x), region.y + int(p.y)
    C["rmb"] = (x, y)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=y)
    ev('RIGHTMOUSE', 'PRESS', x=x, y=y)


@step
def s_rmb_wait():
    redraw()


@step
def s_rmb():
    s = mod("marking.draw").ACTIVE.get("session")
    check("RMB on pCube1 opens the object marking menu", s is not None)
    if s is None:
        return
    rows = [it for it in s.layout.items if it.kind == "list"]
    cols = {round(it.rect[0], 1) for it in rows}
    check(f"G2 the RMB list stays one column near the window bottom ({len(cols)} columns, {len(rows)} rows)",
          len(cols) == 1)
    boxes = list(s.layout.radial.values())
    over = [r.label for r in rows for b in boxes if r.rect[0] < b.rect[2] and b.rect[0] < r.rect[2]
            and r.rect[1] < b.rect[3] and b.rect[1] < r.rect[3]]
    check(f"G2 the list doesn't cover the ring ({over[:3]})", not over)
    # the ring stays at the press point (marks keep working); a list that doesn't fit under it goes beside
    # it (Maya lifts the whole menu only at the screen bottom — Blender's window is
    # smaller than the screen)
    check(f"G2 the ring stays at the press point ({s.center} / {s.press})", s.center == s.press)
    _area, region = main_view()
    cx, cy = s.center
    cx, cy = cx + region.x, cy + region.y      # the session works in the invoking region's pixels
    w = win()
    inside = all(0 <= it.rect[0] + cx and it.rect[2] + cx <= w.width and 0 <= it.rect[1] + cy and
                 it.rect[3] + cy <= w.height for it in rows)
    check("G2 every row inside the window", inside)


@step
def s_rmb_shot():
    shot("rmb_low")
    x, y = C["rmb"]
    ev('RIGHTMOUSE', 'RELEASE', x=x, y=y)
    ev('ESC', 'PRESS', x=x, y=y)
    ev('ESC', 'RELEASE', x=x, y=y)


run()
