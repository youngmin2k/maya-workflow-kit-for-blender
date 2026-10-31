"""In the Maya Workflow Kit layout: Ctrl+1 on group1 isolates it with pCube1 (Maya
isolate select shows the selection's descendants), h on group1 hides pCube1 too while its Visibility channel stays on
(Maya DAG rules). Shots with ``--shots``."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, load_maya_layout, run, screenshot, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    """Window screenshot as (h, w, 3) floats, row 0 = window bottom; also kept in SHOTS."""
    import numpy as np
    path = os.path.join(SHOTS or bpy.app.tempdir, name)
    screenshot(path)
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]


def patch(px, ob, r=5):
    """Pixels around ``ob``'s origin on screen (local view or not: the view matrix is the same)."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    area, region = view3d()
    p = location_3d_to_region_2d(region, region.data, ob.matrix_world.translation)
    x, y = region.x + int(p.x), region.y + int(p.y)
    return px[y - r:y + r + 1, x - r:x + r + 1]


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


def key(k, **mods):
    ev(k, 'PRESS', **mods)
    ev(k, 'RELEASE', **mods)


@step
def s_setup():
    setup()
    load_maya_layout()


step(redraw)
step(redraw)


@step
def s_scene():
    area, region = view3d()
    u = import_module(MODULE + ".operators.units").maya_unit(bpy.context.scene)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
        c1 = bpy.context.active_object
        bpy.ops.allset.create(kind='CUBE')
        c2 = bpy.context.active_object
        c2.location.x = 3 * u
        for o in bpy.context.scene.objects:
            o.select_set(o == c1)
        bpy.context.view_layer.objects.active = c1
        bpy.ops.allset.group()
    g = bpy.context.active_object
    for o in bpy.context.scene.objects:
        o.select_set(o == g)
    C.update(g=g.name, c1=c1.name, c2=c2.name)
    C["mid"] = (area.x + area.width // 2, area.y + area.height // 2)
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    redraw()


step(redraw)


@step
def s_before():
    C["before"] = shot("gui_step164_before.png")
    key('ONE', ctrl=True)


step(redraw)


@step
def s_isolated():
    area, _r = view3d()
    space = area.spaces.active
    g, c1, c2 = (bpy.data.objects[C[k]] for k in ("g", "c1", "c2"))
    check(f"Ctrl+1 on group1 = local view ({space.local_view is not None})", space.local_view is not None)
    check("the selection stays group1 only", g.select_get() and not c1.select_get())
    C["space"] = True


step(redraw)


@step
def s_isolate_shot():
    # Object.local_view_get / visible_in_viewport_get read False for every object here, so the
    # screen decides: pCube1's pixels stay, pCube2's go (screenshots = the frame before, hence one tick later)
    import numpy as np
    px = shot("gui_step164_isolate.png")
    c1, c2 = bpy.data.objects[C["c1"]], bpy.data.objects[C["c2"]]
    d1 = float(np.abs(patch(px, c1) - patch(C["before"], c1)).max())
    d2 = float(np.abs(patch(px, c2) - patch(C["before"], c2)).max())
    check(f"pCube1 (group1's child) is isolated with it (its pixels unchanged, max diff {d1:.3f})", d1 < 0.05)
    check(f"pCube2 is not (its pixels changed, max diff {d2:.3f})", d2 > 0.05)
    key('ONE', ctrl=True)


step(redraw)


@step
def s_h():
    area, _r = view3d()
    check(f"Ctrl+1 again leaves the local view ({area.spaces.active.local_view is None})",
          area.spaces.active.local_view is None)
    key('H')


step(redraw)


@step
def s_hidden():
    g, c1 = bpy.data.objects[C["g"]], bpy.data.objects[C["c1"]]
    check(f"h on group1 hides it ({g.hide_viewport})", g.hide_viewport)
    check(f"pCube1 is not drawn ({c1.visible_get()})", not c1.visible_get())
    check(f"pCube1's own Visibility stays on ({not c1.hide_viewport})", not c1.hide_viewport)


step(redraw)


@step
def s_h_shot():
    shot("gui_step164_h_group.png")
    key('H')


step(redraw)


@step
def s_shown():
    c1 = bpy.data.objects[C["c1"]]
    check(f"h again shows pCube1 ({c1.visible_get()})", c1.visible_get())


run()
