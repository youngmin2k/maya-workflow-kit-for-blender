"""#57: Ctrl+N with unsaved changes asks Maya's Save Changes question (ui/save_prompt.py) — Save / Don't Save
/ Cancel — in the Maya Workflow Kit layout:
cube -> Ctrl+N -> prompt "Warning: Scene Not Saved" / "Save changes to untitled scene?" -> Cancel keeps the cube;
again -> Don't Save = a new empty Maya scene; a saved file + a change -> Ctrl+N -> "Save changes to <path>?" -> Save
writes the file, then the new scene; an untitled scene -> Save = the Save As browser: cancelled = nothing, saved = the
file, then the new scene. Blender's popup menu answers with the underlined letter (S / D / C), like a click on the
button (menu items keep no position: the menu opens with the last answer under the mouse)."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, tap, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tmp", "gui_step138")
os.makedirs(OUT, exist_ok=True)
SAVED = os.path.join(OUT, "prompt_saved.blend")
SAVED_AS = os.path.join(OUT, "prompt_saved_as.blend")
for _p in (SAVED, SAVED_AS):
    if os.path.exists(_p):
        os.remove(_p)
C = {}


def sp():
    return import_module(MODULE + ".ui.save_prompt")


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def strips():
    return [a for a in win().screen.areas if a.type == 'IMAGE_EDITOR'
            and getattr(a.spaces.active, "mask", None) is not None and a.spaces.active.mask.name.startswith(".Allset")]


def meshes():
    return sorted(o.name for o in bpy.data.objects if o.type == 'MESH')


def add_cube():
    area, r = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=r):
        bpy.ops.mesh.primitive_cube_add('EXEC_DEFAULT', True)     # undo push = a modified file
    C["mid"] = (r.x + r.width // 2, r.y + r.height // 2)
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])


def ctrl_n():
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    ev('LEFT_CTRL', 'PRESS')
    ev('N', 'PRESS', ctrl=True)
    ev('N', 'RELEASE', ctrl=True)
    ev('LEFT_CTRL', 'RELEASE')


def wait():
    pass


def save_browser():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            op = getattr(area.spaces.active, "active_operator", None) if area.type == 'FILE_BROWSER' else None
            if op is not None and op.bl_idname == "WM_OT_save_as_mainfile":
                return window, area
    return None, None


# a kit scene carries Maya's hidden startup cameras as objects
STARTUP_CAMERAS = {'persp', 'top', 'front', 'side'}


@step
def s_setup():
    setup()
    load_maya_layout()


step(wait)


@step
def s_cube():
    add_cube()
    check(f"a cube makes the scene modified ({meshes()}, dirty {bpy.data.is_dirty})", bpy.data.is_dirty and meshes())


step(ctrl_n)
step(wait)


@step
def s_prompt():
    shot("gui_step138_prompt_untitled.png")
    check("Ctrl+N on a modified untitled scene asks first (nothing loaded yet)",
          sp()._pending[0] is not None and meshes() == ["Cube"])
    check(f"Maya's texts: {sp().title()!r} / {sp().message()!r}",
          sp().title() == "Warning: Scene Not Saved" and sp().message() == "Save changes to untitled scene?")
    tap('C')      # Cancel


step(wait)
step(wait)


@step
def s_cancelled():
    shot("gui_step138_after_cancel.png")
    check(f"Cancel keeps the scene ({meshes()}, dirty {bpy.data.is_dirty})",
          meshes() == ["Cube"] and bpy.data.is_dirty and sp()._pending[0] is None)


step(ctrl_n)
step(wait)


@step
def s_click_cancel():
    # the menu opens with the last answer (Cancel) under the mouse: a click there answers with the mouse
    shot("gui_step138_prompt_again.png")
    check("asked again", sp()._pending[0] is not None)
    ev('LEFTMOUSE', 'PRESS')
    ev('LEFTMOUSE', 'RELEASE')


step(wait)
step(wait)


@step
def s_click_cancelled():
    check(f"a click on Cancel keeps the scene ({meshes()}, dirty {bpy.data.is_dirty})",
          meshes() == ["Cube"] and bpy.data.is_dirty and sp()._pending[0] is None)


step(ctrl_n)
step(wait)


@step
def s_dont_save():
    tap('D')      # Don't Save


step(wait)
step(wait)
step(wait)


@step
def s_new_scene():
    shot("gui_step138_after_dont_save.png")
    check(f"Don't Save opens a new empty Maya scene ({meshes()}, {len(strips())} strips, file {bpy.data.filepath!r})",
          not meshes() and len(strips()) == 2 and not bpy.data.filepath)
    add_cube()
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.save_as_mainfile(filepath=SAVED)
    C["mtime"] = os.path.getmtime(SAVED)
    check(f"saved as {bpy.data.filepath!r}", os.path.normcase(bpy.data.filepath) == os.path.normcase(SAVED))


step(wait)


@step
def s_modify_saved():
    # a tick after the save: a change made in the save's own tick was marked saved again
    add_cube()      # a second cube: modified again


step(wait)


@step
def s_ctrl_n_saved():
    check(f"saved file modified again (dirty {bpy.data.is_dirty})", bpy.data.is_dirty and len(meshes()) == 2)
    ctrl_n()


step(wait)


@step
def s_prompt_saved():
    shot("gui_step138_prompt_saved.png")
    check(f"a saved scene: {sp().title()!r} / {sp().message()!r}",
          sp().title() == "Save Changes" and sp().message() == f"Save changes to {SAVED}?")
    tap('S')      # Save


step(wait)
step(wait)
step(wait)


@step
def s_saved_then_new():
    with bpy.data.libraries.load(SAVED) as (src, _dst):
        names = sorted(n for n in src.objects if n not in STARTUP_CAMERAS)
    check(f"Save wrote the file first ({names})", len(names) == 2 and os.path.getmtime(SAVED) > C["mtime"])
    check(f"... then the new Maya scene ({meshes()}, file {bpy.data.filepath!r}, {len(strips())} strips)",
          not meshes() and not bpy.data.filepath and len(strips()) == 2)
    add_cube()


step(ctrl_n)
step(wait)


@step
def s_save_untitled():
    tap('S')      # Save on an untitled scene: the Save As browser


step(wait)
step(wait)


@step
def s_browser():
    shot("gui_step138_save_as_browser.png")
    window, area = save_browser()
    check("Save on an untitled scene opens the Save As browser", area is not None)
    if area is not None:
        dirs = os.path.normcase(os.path.normpath(area.spaces.active.params.directory.decode()))
        check(f"... in the project's scenes folder ({dirs})", os.path.basename(dirs) == "scenes")
        with bpy.context.temp_override(window=window, area=area):
            bpy.ops.file.cancel()


step(wait)
step(wait)


@step
def s_browser_cancelled():
    check(f"a cancelled Save As = nothing ({meshes()}, file {bpy.data.filepath!r})",
          meshes() == ["Cube"] and not bpy.data.filepath and save_browser()[1] is None)


step(ctrl_n)
step(wait)
step(lambda: tap('S'))
step(wait)
step(wait)


@step
def s_browser_save():
    window, area = save_browser()
    check("Save As browser again", area is not None)
    if area is not None:
        params = area.spaces.active.params
        params.directory = OUT.encode()
        params.filename = os.path.basename(SAVED_AS)
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.file.execute()


step(wait)
step(wait)
step(wait)


@step
def s_saved_as_then_new():
    shot("gui_step138_after_save_as.png")
    names = []
    if os.path.isfile(SAVED_AS):
        with bpy.data.libraries.load(SAVED_AS) as (src, _dst):
            names = sorted(n for n in src.objects if n not in STARTUP_CAMERAS)
    check(f"Save As wrote the file ({names})", names == ["Cube"])
    check(f"... then the new Maya scene ({meshes()}, file {bpy.data.filepath!r})",
          not meshes() and not bpy.data.filepath and len(strips()) == 2)
    area, r = view3d()
    with bpy.context.temp_override(window=win(), area=area, region=r):
        bpy.ops.object.empty_add()      # no undo push: the scene still counts as unmodified
    C["dirty_before"] = bpy.data.is_dirty


step(ctrl_n)
step(wait)
step(wait)


@step
def s_unmodified():
    check(f"an unmodified scene: Ctrl+N asks nothing (dirty before {C['dirty_before']}, objects "
          f"{len(bpy.data.objects)}, pending {sp()._pending[0]})",
          not C["dirty_before"] and sp()._pending[0] is None and "Empty" not in bpy.data.objects)


run()
