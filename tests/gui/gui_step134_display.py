"""In a real UI (Maya Workflow Kit layout): the Maya display / mode keys (1/2/3, 4-7, F8, F9-F11,
Alt+A) leave no Adjust Last Operation panel (#58), and 3 draws the Maya cube smooth shaded while 1 draws it faceted
(#61): the shading is read along a line across the cube in screenshots."""

import os
import sys
import tempfile

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import check, ev, run, step, setup, screenshot, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}
# Largest step between neighbouring pixels across the cube, as a share of the whole light range along the line.
# Faceted shading = a few flat bands with jumps between them; smooth shading = a gradient. Seen
# with 0.2.1: faceted 3 = 0.21-0.24, 1 = 0.55-0.58; smooth 3 = 0.01-0.03.
SMOOTH_MAX_STEP = 0.1


def key(type, **mods):
    names = {"alt": "LEFT_ALT", "ctrl": "LEFT_CTRL", "shift": "LEFT_SHIFT"}
    for m in mods:
        ev(names[m], 'PRESS')
    ev(type, 'PRESS', **mods)
    ev(type, 'RELEASE', **mods)
    for m in mods:
        ev(names[m], 'RELEASE')


def hud():
    # Blender hides a cleared HUD by zeroing its window rect (hud_region_hide) and keeps its size: a shown
    # panel never sits at the window origin (the status bar is there).
    area, _r = view3d()
    return next((r for r in area.regions if r.type == 'HUD' and r.width > 1 and r.height > 1
                 and (r.x, r.y) != (0, 0)), None)


def cube():
    return bpy.data.objects["pCube1"]


def centre():
    _a, region = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=region.x + region.width // 2, y=region.y + region.height // 2)


def shot_path(name):
    return os.path.join(SHOTS or tempfile.gettempdir(), name)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    bpy.ops.allset.keymap_activate()
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    for o in bpy.context.scene.objects:
        o.select_set(o.name == "pCube1")
    bpy.context.view_layer.objects.active = cube()
    centre()
    # the Maya layout views keep Blender's HUD region off (Maya has no redo panel); turn it on here so the
    # checks below still prove that display / mode keys don't ask for Adjust Last Operation
    with bpy.context.temp_override(window=win(), area=area, region=region):   # no window context = Blender crash
        area.spaces.active.show_region_hud = True
    # Positive control: Alt+W (Blender's object.location_clear: REGISTER + UNDO with a property) leaves its Adjust
    # Last Operation panel (a Python call from a timer, or an operator without properties, shows none).
    # took Shift+H (allset.visibility) off the panel.
    key('W', alt=True)


@step
def s_control():
    h = hud()
    check(f"Alt+W shows Adjust Last Operation (the detector sees a HUD: {h and (h.x, h.y, h.width, h.height)})",
          h is not None)
    centre()
    key('F')                       # frame the cube


# Each key, then one tick later: no HUD. 3 first (it also clears that panel: UNDO without REGISTER).
KEYS = [("THREE", {}), ("TWO", {}), ("ONE", {}), ("FOUR", {}), ("FIVE", {}), ("SIX", {}), ("SEVEN", {}),
        ("FIVE", {}), ("F9", {}), ("F10", {}), ("F11", {}), ("F8", {}), ("F8", {}), ("A", {"alt": True}),
        ("A", {"alt": True}), ("A", {"alt": True})]


def _press(i):
    def fn():
        if i > 0:
            prev, mods = KEYS[i - 1]
            h = hud()
            label = ("Alt+" if mods.get("alt") else "") + prev
            check(f"{label}: no Adjust Last Operation panel ({h and (h.width, h.height)})", h is None)
            if prev == "F9" and SHOTS:
                screenshot(shot_path("gui_step134_after_f9.png"))
        if i < len(KEYS):
            centre()
            k, mods = KEYS[i]
            key(k, **mods)
    fn.__name__ = f"s_key_{i}"
    return fn


for _i in range(len(KEYS) + 1):
    step(_press(_i))


@step
def s_three():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.scene.objects:
        o.select_set(o.name == "pCube1")
    bpy.context.view_layer.objects.active = cube()
    centre()
    key('THREE')


@step
def s_three_deselect():
    h = hud()
    check(f"3 again: no Adjust Last Operation panel ({h and (h.width, h.height)})", h is None)
    cube().select_set(False)       # no selection wire over the shading
    redraw()


@step
def s_three_wait():
    redraw()


@step
def s_three_shot():
    screenshot(shot_path("gui_step134_smooth3.png"))
    C["smooth"] = measure("gui_step134_smooth3.png")


@step
def s_one():
    cube().select_set(True)
    centre()
    key('ONE')


@step
def s_one_deselect():
    cube().select_set(False)
    redraw()


@step
def s_one_wait():
    redraw()


@step
def s_one_shot():
    screenshot(shot_path("gui_step134_smooth1.png"))
    C["flat"] = measure("gui_step134_smooth1.png")
    s, f = C["smooth"], C["flat"]
    print("GUI shading", "3:", s, "1:", f)
    check(f"3 = smooth shaded: no step across the cube larger than {SMOOTH_MAX_STEP} of the range "
          f"(rows {s[0]:.3f} / cols {s[1]:.3f}, range {s[2]:.3f})",
          s[2] > 0.02 and max(s[0], s[1]) < SMOOTH_MAX_STEP)
    check(f"1 = faceted again: a facet edge jump (rows {f[0]:.3f} / cols {f[1]:.3f}, range {f[2]:.3f})",
          max(f[0], f[1]) > SMOOTH_MAX_STEP)


def measure(name):
    """(largest row step, largest column step, light range) over lines through the cube's screen centre."""
    _a, region = view3d()
    bpy.context.view_layer.update()
    ob = cube()
    pts = [location_3d_to_region_2d(region, region.data, ob.matrix_world @ v.co) for v in ob.data.vertices]
    pts = [p for p in pts if p is not None]
    cx = sum(p.x for p in pts) / len(pts)
    cy = sum(p.y for p in pts) / len(pts)
    half = 0.22 * min(max(p.x for p in pts) - min(p.x for p in pts), max(p.y for p in pts) - min(p.y for p in pts))
    img = bpy.data.images.load(shot_path(name))
    w = img.size[0]
    px = img.pixels[:]
    bpy.data.images.remove(img)

    def lum(x, y):
        i = (int(y) * w + int(x)) * 4
        return 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]

    # Lines off the centre: the 3D cursor sits on the cube's origin.
    ox, oy = region.x + cx, region.y + cy
    off = 0.4 * half
    n = max(8, int(2 * half))
    row = [lum(ox - half + 2 * half * k / n, oy + off) for k in range(n + 1)]
    col = [lum(ox + off, oy - half + 2 * half * k / n) for k in range(n + 1)]
    rng = max(max(row) - min(row), max(col) - min(col), 1e-6)

    def worst(line):
        return max(abs(a - b) for a, b in zip(line, line[1:])) / rng

    print("GUI line", name, "centre", (round(ox), round(oy)), "half", round(half),
          "row", [round(v, 3) for v in row[::4]], "col", [round(v, 3) for v in col[::4]])
    return worst(row), worst(col), rng


run()
