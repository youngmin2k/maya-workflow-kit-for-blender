"""#277 in the Maya Workflow Kit layout Time Slider:
- a key at the current frame is marked one frame cell wide (red above and below Blender's current-frame box, nothing
  wider), so the neighbouring keys' ticks stay visible;
- after deselecting everything (the cube stays Blender's active object) no key ticks are drawn.
Run it at UI scale 1.25 and with ALLSET_GUI_UI_SCALE=0.8 (1.0 on this PC)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    path = os.path.join(SHOTS or os.path.join(os.environ.get("TEMP", "."), "gui277"), name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    screenshot(path)
    return path


def timeline():
    for area in win().screen.areas:
        if area.type == 'DOPESHEET_EDITOR' and area.spaces.active.mode == 'TIMELINE':
            return area, next(r for r in area.regions if r.type == 'WINDOW')
    raise LookupError("no timeline")


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def red_mask(path):
    """{(x, y)} of key-red pixels (window coordinates, y from the bottom) inside the Time Slider region."""
    _a, r = timeline()
    im = bpy.data.images.load(path, check_existing=False)
    w, _h = im.size
    px = im.pixels[:]
    bpy.data.images.remove(im)
    out = set()
    for y in range(r.y, r.y + r.height):
        for x in range(r.x, r.x + r.width):
            i = (y * w + x) * 4
            if px[i] > 0.75 and px[i + 1] < 0.25 and px[i + 2] < 0.25:
                out.add((x, y))
    return out


def wx(f):
    """Window x of the frame position ``f`` (a cell edge for f +- 0.5)."""
    _a, r = timeline()
    return r.x + int(r.view2d.view_to_region(f, 0, clip=False)[0])


def tick_x(f):
    _a, r = timeline()
    ts = import_module(MODULE + ".ui.time_slider")
    return r.x + int(ts.key_x(r, f, True))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    ob = bpy.context.active_object
    for f in (10, 13):
        ob.keyframe_insert("location", frame=f)
    bpy.context.scene.frame_set(10)
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 3)
    redraw()


@step
def s_wait():
    redraw()


@step
def s_current_key():
    path = shot("gui_issue277_key_current.png")
    red = red_mask(path)
    _a, r = timeline()
    left, right = wx(9.5), wx(10.5)
    w = max(1, round(bpy.context.preferences.system.ui_scale))
    cell = {(x, y) for x, y in red if left - 1 <= x <= right + w}
    t13 = tick_x(13)
    other = {(x, y) for x, y in red if (x, y) not in cell and not (t13 - 1 <= x <= t13 + w)}
    rows = sorted({y for _x, y in cell})
    C["cell_px"] = right - left
    print("GUI INFO cell", left, right, "red rows", rows, "red cols",
          sorted({x for x, _y in cell}), "other", sorted({x for x, _y in other})[:20], flush=True)
    check(f"#277-3: the key at the current frame shows red ({len(cell)} px)", len(cell) >= 6)
    check(f"#277-3: red above and below the current-frame box ({rows})",
          bool(rows) and min(rows) <= r.y + 3 and max(rows) >= r.y + r.height - 4)
    cols = sorted({x for x, _y in cell})
    width = (cols[-1] - cols[0] + 1) if cols else 0
    check(f"#277-3: the current-frame key mark is no wider than one frame cell ({width} px, cell {right - left} px)",
          0 < width <= right - left + w)
    check(f"#277-3: no red beside the current frame's cell (was a frame around the box) ({len(other)} px)",
          not other)
    n13 = sum(1 for x, _y in red if t13 - 1 <= x <= t13 + w)
    check(f"#277-3: the key two frames on keeps its full tick ({n13} px, region {r.height} px)",
          n13 >= r.height - 2)


@step
def s_neighbour():
    # a key on the next frame: its tick lies under Blender's box; the parts above / below the box show
    ob = bpy.data.objects["pCube1"]
    ob.keyframe_insert("location", frame=11)
    redraw()


@step
def s_neighbour_wait():
    redraw()


@step
def s_neighbour_shot():
    path = shot("gui_issue277_key_neighbour.png")
    red = red_mask(path)
    t11 = tick_x(11)
    _a, r = timeline()
    n = sum(1 for x, _y in red if t11 <= x <= t11 + 1)
    check(f"#277-3: the next frame's key tick still shows beside the box ({n} px)", n >= 2)


@step
def s_deselect():
    bpy.ops.object.select_all(action='DESELECT')
    check("Blender keeps the deselected cube active", bpy.context.view_layer.objects.active is not None)
    bpy.context.scene.frame_set(20)
    redraw()


@step
def s_deselect_wait():
    redraw()


@step
def s_deselect_shot():
    path = shot("gui_issue277_deselected.png")
    red = red_mask(path)
    check(f"#277-2: nothing selected = no key ticks on the Time Slider ({len(red)} red px)", not red)
    bpy.data.objects["pCube1"].select_set(True)
    redraw()


@step
def s_reselect_wait():
    redraw()


@step
def s_reselect_shot():
    path = shot("gui_issue277_reselected.png")
    red = red_mask(path)
    check(f"#277-2: selecting the cube again shows its ticks ({len(red)} red px)", len(red) >= 20)


run()
