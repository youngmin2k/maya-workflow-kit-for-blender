"""In a real UI (Maya scene workflow): File > Project Window (dialog shot) -> project
folders made -> Ctrl+Shift+S opens the file browser in <project>/scenes -> save shot_v001 -> Ctrl+Alt+S = Maya Increment
and Save -> shot_v001.0001 -> Ctrl+R opens the browser in scenes -> reference shot_v001 as prop -> prop:pCube1 ->
File > Reference Editor = the kit Reference Editor window listing propRN (screenshots)."""

import os
import shutil
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, setup, step, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tmp", "gui69")
C = {}


def mod(name):
    return import_module(MODULE + name)


def shot(name, window=None):
    if SHOTS:
        with bpy.context.temp_override(window=window or win()):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def run_menu(path):
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        return mod(".marking.modal").run_action(bpy.context, mod(".ui.menu_map").MAP[path])


def key(type, **mods):
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    ev(type, 'PRESS', x=C["mid"][0], y=C["mid"][1], **mods)
    ev(type, 'RELEASE', x=C["mid"][0], y=C["mid"][1], **mods)


def file_browser():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'FILE_BROWSER' and a.spaces.active.params is not None:
                return w, a
    return None, None


def close_browser():
    w, a = file_browser()
    if w is None:
        return
    r = next(r for r in a.regions if r.type == 'WINDOW')
    x, y = r.x + r.width // 2, r.y + r.height // 2
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    w.event_simulate(type='ESC', value='PRESS', x=x, y=y)
    w.event_simulate(type='ESC', value='RELEASE', x=x, y=y)


def browser_dir():
    _w, a = file_browser()
    return os.path.normcase(os.path.normpath(bpy.path.abspath(a.spaces.active.params.directory.decode()
                                                              if isinstance(a.spaces.active.params.directory, bytes)
                                                              else a.spaces.active.params.directory))) if a else None


def scenes():
    return os.path.normcase(os.path.join(ROOT, "proj69", "scenes"))


@step
def s_setup():
    setup()
    bpy.ops.allset.keymap_activate()
    shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(ROOT)
    _a, r = view3d()
    C["mid"] = (r.x + r.width // 2, r.y + r.height // 2)
    bpy.data.objects["Cube"].name = "pCube1"
    ev('ESC', 'PRESS', x=C["mid"][0], y=C["mid"][1])     # the first-run splash (Quick Setup) again
    ev('ESC', 'RELEASE', x=C["mid"][0], y=C["mid"][1])


@step
def s_open_project_window():
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    C["pw"] = run_menu("File/Project Window")


@step
def s_project_dialog():
    shot("gui_step69_project_window.png")
    ev('ESC', 'PRESS', x=C["mid"][0], y=C["mid"][1])
    ev('ESC', 'RELEASE', x=C["mid"][0], y=C["mid"][1])


@step
def s_project_made():
    # the dialog's Accept, with the test folder as location
    bpy.ops.allset.project_window(name="proj69", location=ROOT)
    root = os.path.join(ROOT, "proj69")
    have = [d for d in ("scenes", "sourceimages", "images", "renderData") if os.path.isdir(os.path.join(root, d))]
    check(f"File > Project Window (got {C['pw']}): Accept makes Maya's folders ({have}) and the current project",
          len(have) == 4 and os.path.normcase(mod(".operators.project").current_root()) == os.path.normcase(root))
    key('S', ctrl=True, shift=True)


@step
def s_save_as_browser():
    if file_browser()[0] is None and C.setdefault("w1", 0) < 10:
        C["w1"] += 1
        sys.modules["sim"]._steps.insert(0, s_save_as_browser)
        return
    got = browser_dir()
    check(f"Ctrl+Shift+S: the file browser starts in <project>/scenes (got {got})", got == scenes())
    w, _a = file_browser()
    shot("gui_step69_save_as.png", w)
    close_browser()


@step
def s_saved():
    path = os.path.join(ROOT, "proj69", "scenes", "shot_v001.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    C["src"] = path
    check(f"saved in the project: render output = //../images/ (got {bpy.context.scene.render.filepath})",
          bpy.context.scene.render.filepath == "//../images/")
    key('S', ctrl=True, alt=True)


@step
def s_incremented():
    name = os.path.basename(bpy.data.filepath)
    check(f"Ctrl+Alt+S = Maya Increment and Save: shot_v001.0001.blend, shot_v001.blend kept (got {name})",
          name == "shot_v001.0001.blend" and os.path.isfile(C["src"]))
    key('R', ctrl=True)


@step
def s_reference_browser():
    if file_browser()[0] is None and C.setdefault("w2", 0) < 10:
        C["w2"] += 1
        sys.modules["sim"]._steps.insert(0, s_reference_browser)
        return
    got = browser_dir()
    check(f"Ctrl+R = Create Reference: the file browser starts in <project>/scenes (got {got})", got == scenes())
    close_browser()


@step
def s_referenced():
    area, region = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=region):
        res = bpy.ops.allset.create_reference(filepath=C["src"], namespace="prop")
    ob = bpy.data.objects.get("prop:pCube1")
    check(f"Create Reference shot_v001 as prop: prop:pCube1, editable override (got {res}, {ob is not None})",
          ob is not None and ob.override_library is not None)
    C["nwin"] = len(bpy.context.window_manager.windows)
    C["re"] = run_menu("File/Reference Editor")


@step
def s_reference_editor():
    w = bpy.context.window_manager.windows[-1]
    a = w.screen.areas[0]
    re_ = import_module(MODULE + ".ui.reference_editor")
    refs = import_module(MODULE + ".operators.references")
    listed = [(refs.node_name(r), refs.file_label(r)) for r in refs.references()]
    # Maya's Reference Editor window (was an Outliner in Blender File view)
    check(f"File > Reference Editor: the kit Reference Editor window listing propRN shot_v001.blend "
          f"(got {C['re']}, {a.type}, {listed})",
          len(bpy.context.window_manager.windows) == C["nwin"] + 1 and re_.is_pane(a)
          and ("propRN", "shot_v001.blend") in listed)
    C["rew"] = w
    for ar in w.screen.areas:
        ar.tag_redraw()


@step
def s_end():
    shot("gui_step69_reference_editor.png", C["rew"])
    shot("gui_step69_outliner.png")


run()
