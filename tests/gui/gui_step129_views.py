"""Viewport lane in a real UI:
#8  Tool Box quick layouts: Four View = top / persp / front / side; Single Perspective is always persp, also after a
    Space tap left the four view on the top panel;
#9  F / Alt+LMB in a view that looks through a created camera move that camera and keep the camera view; a locked
    camera (toolbar Lock Camera) stays;
#24 IPR off gives Wireframe back; #13 UV checker button turns off again."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, screenshot, setup, step, tap, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def ov(fn, **kw):
    area, region = view3d()
    region = mod("ui.panel_menus").main_region(area)
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return fn(**kw)


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, f"gui_step129_{name}.png"))


def quads():
    """{position: WINDOW region} of the four view (tl, tr, bl, br). The four view is four real 3D View
    areas (ui/four_view.py), not one area's Quad View regions."""
    areas = mod("ui.four_view").panes(win().screen)
    cx = sum(a.x + a.width / 2 for a in areas) / max(len(areas), 1)
    cy = sum(a.y + a.height / 2 for a in areas) / max(len(areas), 1)
    out = {}
    for a in areas:
        r = next(r for r in a.regions if r.type == 'WINDOW')
        out[("t" if a.y + a.height / 2 > cy else "b") + ("l" if a.x + a.width / 2 < cx else "r")] = r
    return out


def axis_name(rv3d):
    if rv3d.view_perspective != 'ORTHO':
        return rv3d.view_perspective
    from mathutils import Vector
    d = rv3d.view_rotation @ Vector((0, 0, -1))
    for name, v in (("top", (0, 0, -1)), ("front", (0, 1, 0)), ("side", (-1, 0, 0))):
        if (d - Vector(v)).length < 1e-3:
            return name
    return "ortho"


def moved(m0, m1):
    return max(abs(a - b) for ra, rb in zip(m0, m1) for a, b in zip(ra, rb))


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_four():
    bpy.ops.allset.keymap_activate()
    sp = view3d()[0].spaces.active
    C["persp"] = tuple(round(v, 4) for v in sp.region_3d.view_rotation)
    ov(bpy.ops.allset.quick_layout, layout='FOUR')


@step
def s_four_check():
    q = quads()
    names = {k: axis_name(r.data) for k, r in q.items()}
    check(f"#8 Four View = top / persp / front / side like Maya ({names})",
          names == {"tl": "top", "tr": "PERSP", "bl": "front", "br": "side"})
    shot("four")
    tl = q["tl"]
    ev('MOUSEMOVE', 'NOTHING', x=tl.x + tl.width // 2, y=tl.y + tl.height // 2)


@step
def s_space_top():
    tap('SPACE')


@step
def s_single_after_space():
    sp = view3d()[0].spaces.active
    check(f"Space tap over the top panel maximises top ({axis_name(sp.region_3d)})",
          not sp.region_quadviews and axis_name(sp.region_3d) == "top")
    ov(bpy.ops.allset.quick_layout, layout='SINGLE')


@step
def s_single_check():
    sp = view3d()[0].spaces.active
    rot = tuple(round(v, 4) for v in sp.region_3d.view_rotation)
    check(f"#8 Single Perspective View after that shows persp, not top ({axis_name(sp.region_3d)}, {rot})",
          not sp.region_quadviews and sp.region_3d.view_perspective == 'PERSP' and rot == C["persp"])
    shot("single")
    # single top -> Four View: the top right panel is persp again
    ov(bpy.ops.allset.hb_view, view='TOP')
    ov(bpy.ops.allset.quick_layout, layout='FOUR')


@step
def s_four_from_top():
    names = {k: axis_name(r.data) for k, r in quads().items()}
    check(f"#8 Four View from a single top view keeps Maya's panels ({names})",
          names == {"tl": "top", "tr": "PERSP", "bl": "front", "br": "side"})
    ov(bpy.ops.allset.quick_layout, layout='SINGLE')


@step
def s_camera():
    sp = view3d()[0].spaces.active
    check(f"#8 back to Single Perspective: persp ({axis_name(sp.region_3d)})",
          not sp.region_quadviews and sp.region_3d.view_perspective == 'PERSP')
    ov(bpy.ops.allset.create, kind='CUBE')
    cube = bpy.context.view_layer.objects.active
    cube.location = (8.0, 6.0, 2.0)
    C["cube"] = cube.name
    ov(bpy.ops.allset.create, kind='CAMERA')
    cam = bpy.context.view_layer.objects.active
    cam.location = (0.0, -40.0, 10.0)
    cam.rotation_euler = (1.3, 0.0, 0.0)
    C["cam"] = cam.name
    ov(bpy.ops.allset.panel_look_through, camera=cam.name)
    for ob in bpy.context.scene.objects:
        ob.select_set(ob == cube)
    bpy.context.view_layer.objects.active = cube
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)


@step
def s_f():
    C["m0"] = bpy.data.objects[C["cam"]].matrix_world.copy()
    tap('F')


@step
def s_f_check():
    sp = view3d()[0].spaces.active
    cam, cube = bpy.data.objects[C["cam"]], bpy.data.objects[C["cube"]]
    from bpy_extras.object_utils import world_to_camera_view
    bpy.context.view_layer.update()
    from mathutils import Vector
    uv = [world_to_camera_view(bpy.context.scene, cam, cube.matrix_world @ Vector(c)) for c in cube.bound_box]
    p = Vector(((min(q.x for q in uv) + max(q.x for q in uv)) / 2, (min(q.y for q in uv) + max(q.y for q in uv)) / 2))
    check(f"#9 F in camera1's view keeps the camera view ({sp.region_3d.view_perspective})",
          sp.region_3d.view_perspective == 'CAMERA' and sp.camera == cam)
    check(f"#9 F moved camera1 to frame the cube (moved {moved(C['m0'], cam.matrix_world):.2f}, box centre at {p.x:.2f}, "
          f"{p.y:.2f})", moved(C["m0"], cam.matrix_world) > 1e-3 and abs(p.x - 0.5) < 0.05 and abs(p.y - 0.5) < 0.05)
    shot("camera_f")
    C["m0"] = cam.matrix_world.copy()


def alt_drag(tag):
    def a():
        _a, r = view3d()
        C["c"] = (r.x + r.width // 2, r.y + r.height // 2)
        ev('MOUSEMOVE', 'NOTHING', x=C["c"][0], y=C["c"][1])

    def b():
        ev('LEFTMOUSE', 'PRESS', alt=True)

    def c():
        ev('MOUSEMOVE', 'NOTHING', x=C["c"][0] + 80, y=C["c"][1] + 30, alt=True)

    def d():
        ev('MOUSEMOVE', 'NOTHING', x=C["c"][0] + 160, y=C["c"][1] + 60, alt=True)

    def e():
        ev('LEFTMOUSE', 'RELEASE', alt=True)
    for f in (a, b, c, d, e):
        step(f)


alt_drag("free")


@step
def s_tumble_check():
    sp = view3d()[0].spaces.active
    cam = bpy.data.objects[C["cam"]]
    check(f"#9 Alt+LMB tumble moves camera1 and stays in its view (moved {moved(C['m0'], cam.matrix_world):.2f}, "
          f"{sp.region_3d.view_perspective})",
          moved(C["m0"], cam.matrix_world) > 1e-3 and sp.region_3d.view_perspective == 'CAMERA')
    ov(bpy.ops.allset.panel_set, key='CAMERA_LOCK', toggle=True)
    C["m0"] = cam.matrix_world.copy()


alt_drag("locked")


@step
def s_locked_check():
    sp = view3d()[0].spaces.active
    cam = bpy.data.objects[C["cam"]]
    check(f"Lock Camera: Alt+LMB doesn't move camera1 ({moved(C['m0'], cam.matrix_world):.4f}, "
          f"{sp.region_3d.view_perspective})",
          moved(C["m0"], cam.matrix_world) < 1e-5 and sp.region_3d.view_perspective == 'CAMERA')
    tap('F')


@step
def s_locked_f():
    cam = bpy.data.objects[C["cam"]]
    check("Lock Camera: F doesn't move camera1", moved(C["m0"], cam.matrix_world) < 1e-5)
    ov(bpy.ops.allset.panel_set, key='CAMERA_LOCK', toggle=True)
    # #24 IPR from Wireframe
    sp = view3d()[0].spaces.active
    sp.region_3d.view_perspective = 'PERSP'
    sp.shading.type = 'WIREFRAME'
    # the viewport's own Rendered toggle (IPR itself opens its own window: gui_issue277_ipr)
    mod("ui.status_line").ipr_toggle(sp)
    C["ipr_on"] = sp.shading.type


@step
def s_ipr_off():
    mod("ui.status_line").ipr_toggle(view3d()[0].spaces.active)


@step
def s_ipr_check():
    sp = view3d()[0].spaces.active
    check(f"#24 IPR on then off from Wireframe gives Wireframe back ({C['ipr_on']} -> {sp.shading.type})",
          C["ipr_on"] == 'RENDERED' and sp.shading.type == 'WIREFRAME')
    sp.shading.type = 'SOLID'
    mi = mod("operators.menu_items")
    states = [mi.checker_on(bpy.context)]
    for _i in range(2):
        ov(bpy.ops.allset.editor_icon, key="UV Editor|checker_tiles")
        states.append(mi.checker_on(bpy.context))
    check(f"#13 UV Editor checker button: off -> on -> off ({states})", states == [False, True, False])


run()
