"""#277 in a real UI: Maya Workflow Kit layout -> new scene (no scene camera) -> Cube -> Render > Render Current Frame
(the Maya menu item) -> a Render window (Image Editor on Render Result) whose image shows the cube, rendered through
the scene's startup persp placed where the view looks from, instead of Blender's "No camera found". The Status Line
Render button's operator renders again through the same persp. Screenshots: gui_issue277_render_view.png,
gui_issue277_main.png."""

import os
import sys
import tempfile
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, load_maya_layout, run, setup, step, win  # noqa: E402

GUI_TIMEOUT = 240
SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def v3d():
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def redraw_all():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def render_window():
    """(window, area) of an Image Editor showing the Render Result in a window other than the main one."""
    for w in bpy.context.window_manager.windows[1:]:
        for a in w.screen.areas:
            img = getattr(a.spaces.active, "image", None) if a.type == 'IMAGE_EDITOR' else None
            if img is not None and img.type == 'RENDER_RESULT':
                return w, a
    return None, None


def wait(fn, cond, limit=150):
    """Run ``fn`` again next tick until ``cond()`` or ``limit`` ticks."""
    C.setdefault(fn.__name__, 0)
    if not cond() and C[fn.__name__] < limit:
        C[fn.__name__] += 1
        sys.modules["sim"]._steps.insert(0, fn)
        return True
    return False


@step
def s_setup():
    setup()
    bpy.ops.allset.make_maya(open_layout=False)
    load_maya_layout()


@step
def s_new_scene():
    bpy.ops.allset.keymap_activate()
    sc = bpy.context.scene
    C["camera_before"] = sc.camera
    C["objects_before"] = len(bpy.data.objects)
    sc.render.resolution_percentage = 25        # speed only: the camera path is checked, not the look
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        bpy.ops.allset.create(kind='CUBE')
    C["cube"] = bpy.context.active_object.name
    redraw_all()


@step
def s_render():
    check(f"New Maya scene: no camera in the file before the render (scene.camera {C['camera_before']}, "
          f"{C['objects_before']} objects), cube {C['cube']}", C["camera_before"] is None and C["cube"])
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["ret"] = bpy.ops.allset.menu_item('INVOKE_DEFAULT', item="Render/Render Current Frame")


@step
def s_rendered():
    if wait(s_rendered, lambda: not bpy.app.is_job_running('RENDER') and render_window()[0] is not None):
        redraw_all()
        return
    w, a = render_window()
    sc = bpy.context.scene
    cam = sc.camera
    check(f"Render > Render Current Frame: a Render View window with the Render Result (menu {C['ret']}, "
          f"window {w is not None})", w is not None)
    # a kit new Maya scene renders through Maya's startup persp (a hidden Outliner row, not a second one)
    check(f"rendered through persp: scene.camera {cam and cam.name} (startup {cam and cam.get('allset_startup_camera')}), "
          f"lens {cam and round(cam.data.lens, 3)} mm, hidden",
          cam is not None and cam.name == "persp" and cam.get("allset_startup_camera") == "persp" and cam.hide_viewport)
    image = mod(".ui.render_view").render_result()
    path = os.path.join(SHOTS or tempfile.gettempdir(), "gui_issue277_render_result.png")
    ok = False
    try:
        image.save_render(filepath=path)
        ok = True
    except RuntimeError as ex:
        C["err"] = str(ex)
    stats = (0, 0, 0, 1.0, 1.0)
    if ok:
        img = bpy.data.images.load(path)
        px = list(img.pixels)
        wd, ht = img.size
        bg = px[0:3]
        hits = [(k % wd, k // wd) for k in range(wd * ht)
                if max(abs(px[4 * k + c] - bg[c]) for c in range(3)) > 0.03]
        cx = sum(x for x, _y in hits) / len(hits) / wd if hits else 1.0
        cy = sum(y for _x, y in hits) / len(hits) / ht if hits else 1.0
        stats = (wd, ht, len(hits), cx, cy)
        C["cube_mean"] = (sum(max(px[4 * (y * wd + x) + c] for c in range(3)) for x, y in hits) / len(hits)
                          if hits else 0.0)
        bpy.data.images.remove(img)
    # The template view looks at the origin from Maya's persp distance (cm scene), so the 2 cm cube is small and in the
    # middle of the frame, like in the viewport.
    check(f"the Render Result has pixels and shows the cube where the view shows it (size {stats[0]}x{stats[1]}, "
          f"{stats[2]} cube pixels, centre at {stats[3]:.2f} / {stats[4]:.2f} of the frame{C.get('err', '')})",
          ok and stats[0] > 0 and 30 < stats[2] < stats[0] * stats[1] // 2
          and abs(stats[3] - 0.5) < 0.1 and abs(stats[4] - 0.5) < 0.1)
    C["rv"] = (w, a)
    redraw_all()


@step
def s_shots():
    w, _a = C["rv"]
    shot("gui_issue277_render_view.png", w)
    shot("gui_issue277_main.png")
    # second render from the Status Line Render button's operator: the same persp object, still one
    area, region = v3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        C["ret2"] = bpy.ops.allset.render('INVOKE_DEFAULT')


@step
def s_again():
    if wait(s_again, lambda: not bpy.app.is_job_running('RENDER')):
        return
    persps = [o.name for o in bpy.data.objects if o.type == 'CAMERA' and o.name.startswith("persp")]
    check(f"render again from the Status Line button's operator ({C['ret2']}): persp reused ({persps})",
          persps == ["persp"] and C["ret2"] == {'FINISHED'})
    # close the render windows this test opened
    for w in list(bpy.context.window_manager.windows[1:]):
        with bpy.context.temp_override(window=w):
            bpy.ops.wm.window_close()


@step
def s_closed():
    check(f"render windows closed ({len(bpy.context.window_manager.windows)} window left)",
          len(bpy.context.window_manager.windows) == 1)


run()
