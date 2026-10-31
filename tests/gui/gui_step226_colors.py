"""Lane B (#136): measure that a kit Wireframe Color shows on an unselected curve's wire in a Maya layout view
(solid shading; operators/wire_color.py sets the view's wireframe_color_type to 'OBJECT' and Object.color in scene
linear). Screenshot pixels of the curve: none red before, red after index 13, and the colour of index 18 after it
(sRGB -> linear conversion right: the drawn pixel is Maya's sRGB value, not its linear one)."""

import os
import sys
import tempfile
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, screenshot, setup, step, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def area3d():
    return max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def pixels(name):
    path = os.path.join(SHOTS or tempfile.gettempdir(), f"gui_step226_{name}.png")
    screenshot(path)
    img = bpy.data.images.load(path)
    w, _h = img.size
    px = img.pixels[:]
    bpy.data.images.remove(img)
    a = area3d()
    out = []
    for y in range(a.y + 40, a.y + a.height - 40):
        for x in range(a.x + 40, a.x + a.width - 40, 1):
            i = (y * w + x) * 4
            out.append((px[i], px[i + 1], px[i + 2]))
    return out


def near(pxs, rgb, tol=0.03):
    return sum(1 for p in pxs if all(abs(p[k] - rgb[k]) <= tol for k in range(3)))


def reddish(pxs):
    """Pixels of a 1 px anti-aliased red wire: red clearly above green and blue (the grey background has r = g = b)."""
    return sum(1 for p in pxs if p[0] - max(p[1], p[2]) > 0.12)


def strongest(pxs, bg):
    """The wire pixel furthest from the flat background (the line's core, least mixed with it)."""
    return max(pxs, key=lambda p: sum((p[k] - bg[k]) ** 2 for k in range(3)))


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_curve():
    wc = import_module(MODULE + ".operators.wire_color")
    C["wc"] = wc
    for ob in list(bpy.context.scene.objects):
        ob.select_set(False)
    # a thick ring: many pixels of the wire, all unselected
    bpy.ops.curve.primitive_bezier_circle_add(radius=4.0, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.select_set(False)
    bpy.context.view_layer.objects.active = None
    C["ob"] = ob
    space = area3d().spaces.active
    space.shading.type = 'SOLID'
    C["type0"] = space.shading.wireframe_color_type
    with bpy.context.temp_override(window=win(), area=area3d(),
                                   region=next(r for r in area3d().regions if r.type == 'WINDOW')):
        bpy.ops.view3d.view_all()
    redraw()


@step
def s_before():
    C["before"] = reddish(pixels("before"))


@step
def s_red():
    C["wc"].set_override(C["ob"], enabled=True, index=13)
    C["type1"] = area3d().spaces.active.shading.wireframe_color_type
    redraw()


@step
def s_red_shot():
    C["red"] = reddish(pixels("red"))


@step
def s_cyan():
    C["wc"].set_override(C["ob"], index=18)
    redraw()


@step
def s_cyan_shot():
    pxs = pixels("cyan")
    srgb = C["wc"].PALETTE[18]
    from mathutils import Color
    lin = Color(srgb).from_srgb_to_scene_linear()
    bg = max(set(pxs), key=pxs.count)
    tinted = [p for p in pxs if max(p) - min(p) > 0.12] or pxs   # the coloured wire only (ViewCube / text are grey)
    core = strongest(tinted, bg)
    dist = lambda c: sum((core[k] - c[k]) ** 2 for k in range(3)) ** 0.5  # noqa: E731
    C["cyan_srgb"] = round(dist(srgb), 3)        # distance of the line core to each candidate
    C["cyan_lin"] = round(dist((lin.r, lin.g, lin.b)), 3)
    C["core"] = tuple(round(v, 3) for v in core)
    print("GUI measure wire type", C["type0"], "->", C["type1"], "red before", C["before"], "after", C["red"],
          "index 18 as sRGB", C["cyan_srgb"], "as linear", C["cyan_lin"], flush=True)
    check(f"Maya layout view switched to object wire colours ({C['type0']} -> {C['type1']})",
          C["type0"] == 'THEME' and C["type1"] == 'OBJECT')
    check(f"no red wire before ({C['before']} px)", C["before"] < 5)
    check(f"unselected curve wire drawn in override index 13 red ({C['red']} px)", C["red"] > 50)
    check(f"index 18 line core {C['core']} nearer Maya's sRGB value ({C['cyan_srgb']}) than the linear one "
          f"({C['cyan_lin']})", C["cyan_srgb"] < C["cyan_lin"])


@step
def s_off():
    C["wc"].set_override(C["ob"], enabled=False)
    check("Enable Overrides off: the view is back to theme wire colours",
          area3d().spaces.active.shading.wireframe_color_type == 'THEME')


run()
