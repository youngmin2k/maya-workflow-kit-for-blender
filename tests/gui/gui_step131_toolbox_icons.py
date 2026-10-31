"""Lane TOOLBOX (#23) in a real UI: the Maya Workflow Kit layout's Tool Box column shows the kit-drawn Maya
tool and quick-layout icons (unscaled, at the toolbar's icon size), the Layer Editor toolbar and the Outliner's
default rows show kit glyphs in Maya-style colours, and a Tool Box click still sets the tool. Screenshots of the
column / Outliner / Layer Editor go to ALLSET_GUI_SHOTS (run once with --ui-scale 0.8 = effective 1.0 on a 125 %
display, once without)."""

import os
import sys
from importlib import import_module

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, dock_area, ev, run, scale, screenshot, setup, step, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
toolbox = import_module(MODULE + ".ui.toolbox")
ki = import_module(MODULE + ".ui.kit_icons")
osets = import_module(MODULE + ".ui.outliner_sets")
TEAL = np.array(ki.TEAL)
LIGHT = np.array(ki.LIGHT)
C = {}


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def column():
    return next((a for a in win().screen.areas if toolbox.is_toolbox(a.spaces.active)), None)


def tools_region():
    return next(r for r in column().regions if r.type == 'TOOLS')


def tool_y(i):
    """Centre of the i-th Tool Box button (gui_step49_layout.tool_y)."""
    r = tools_region()
    return round(r.y + r.height - scale() * (23 + 35 * i))


def shot_pixels():
    """Window screenshot as (h, w, 4) floats, row 0 = window bottom (region coordinates)."""
    path = os.path.join(bpy.app.tempdir, "allset_step131_shot.png")
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    if SHOTS:
        import shutil
        shutil.copy(path, os.path.join(SHOTS, f"step131_window_{scale():.2f}.png"))
    return px.reshape(h, w, 4)


def near(px, colour, tol=0.07):
    return np.abs(px[..., :3] - colour).max(axis=-1) < tol


def bbox(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_scene():
    redraw()


@step
def s_wait():
    dock_area('CHANNEL_BOX')
    redraw()


@step
def s_wait2():
    redraw()


@step
def s_check():
    from bl_ui import space_toolsystem_common as stc
    keys = [k for k in stc._icon_cache if k.startswith("allset.tool:")]
    check(f"the Tool Box tools draw kit icons ({len(keys)} kit names in Blender's toolbar icon cache)",
          {f"allset.tool:{t}@{round(ki.icon_saturation(), 3)}" for t in toolbox.MAYA_TOOLS} <= set(keys))
    px = shot_pixels()
    C["px"] = px
    r = tools_region()
    half = round(17 * scale())
    # Move = 4th button: four teal arrowheads round a light square, at the toolbar's tool icon size (a vector
    # icon like Blender's own; a button icon would be 16 px x scale)
    cy = tool_y(3)
    cx = r.x + r.width // 2
    crop = px[cy - half:cy + half, r.x:r.x + r.width]
    teal = near(crop, TEAL)
    b = bbox(teal)
    print("MOVE teal bbox on screen", b, "scale", scale())
    check(f"Move tool icon shows Maya's teal arrows ({int(teal.sum())} px)", teal.sum() > 20)
    h = b and (b[3] - b[1] + 1)
    check(f"Move tool icon at tool size: arrows span {h} px (> 20 x scale)", h is not None and h > 20 * scale())
    if SHOTS:
        C["tb"] = (r.x, r.y, r.width, r.height)
    # quick layout buttons under the tools: light grey framed glyphs (Blender's VIEW_PERSPECTIVE is line art)
    below = px[r.y:tool_y(5) - half, r.x:r.x + r.width]
    check(f"quick layout icons in the Maya-style grey ({int(near(below, LIGHT, 0.05).sum())} px)", near(below, LIGHT, 0.05).sum() > 60)
    # Outliner default rows: the set ring has a teal flag, the cameras a grey body
    outl = next(a for a in win().screen.areas if a.type == 'OUTLINER')
    reg = next(rg for rg in outl.regions if rg.type == 'WINDOW')
    rows = osets.REGIONS.get(reg.as_pointer(), [])
    u = osets.unit(bpy.context.preferences)
    n_small = ki.size_for("outliner:SET", scale())
    sets_ = [rw for rw in rows if rw[2] == 'DEFAULT_SET']
    if sets_:
        y0, y1 = sets_[0][0], sets_[0][1]
        lead = u if outl.spaces.active.show_mode_column else 0   # no mode column in the Maya Outliner
        cxi = reg.x + round(lead + 1.5 * u)
        cyi = reg.y + round((y0 + y1) / 2)
        crop = px[cyi - n_small // 2 - 1:cyi + n_small // 2 + 1, cxi - n_small // 2 - 1:cxi + n_small // 2 + 1]
        t = near(crop, TEAL, 0.06)
        print("SET teal", int(t.sum()), "mean", crop[..., :3].reshape(-1, 3)[t.reshape(-1)].mean(axis=0) if t.any() else None)
        check(f"Outliner set row icon: Maya teal flag in the right colour ({int(t.sum())} px)", t.sum() >= 3)
    else:
        check("Outliner default set rows drawn", False)
    # Layer Editor toolbar in the tab stack: teal arrows / plus / ball
    stack = dock_area()
    sreg = next(rg for rg in stack.regions if rg.type == 'WINDOW')
    crop = px[sreg.y:sreg.y + sreg.height, sreg.x:sreg.x + sreg.width]
    # the dock's additive lift to the dock grey (maya_dock.draw_tint) also lifts the icons drawn under it
    lift = import_module(MODULE + ".ui.maya_dock").dock_lift(bpy.context)
    t = near(crop, np.clip(TEAL + lift, 0.0, 1.0))
    check(f"Layer Editor toolbar icons in the Maya-style teal ({int(t.sum())} px)", t.sum() > 12)
    if SHOTS:
        save_crops(px, r, reg, sreg)
    # a Tool Box click still sets the tool (Rotate)
    ev('MOUSEMOVE', 'NOTHING', x=cx, y=tool_y(4))
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


def save_crops(px, tb, outl, stack):
    s = f"{scale():.2f}"
    for name, rg, extra in (("toolbox", tb, 0), ("outliner", outl, 0), ("stack", stack, 0)):
        crop = px[rg.y:rg.y + rg.height, rg.x:rg.x + rg.width]
        if name == "outliner":
            crop = crop[-min(crop.shape[0], round(260 * scale())):]
        if name == "stack":
            crop = crop[:min(crop.shape[0], round(300 * scale()))]
        h, w = crop.shape[:2]
        img = bpy.data.images.new(f"crop_{name}", w, h, alpha=True)
        img.pixels.foreach_set(np.ascontiguousarray(crop).ravel())
        img.filepath_raw = os.path.join(SHOTS, f"step131_{name}_{s}.png")
        img.file_format = 'PNG'
        img.save()
        bpy.data.images.remove(img)


@step
def s_clicked():
    tool = bpy.context.workspace.tools.from_space_view3d_mode('OBJECT', create=False).idname
    check(f"Tool Box Rotate button (kit icon) sets the Rotate tool ({tool})", tool == "builtin.rotate")


run()
