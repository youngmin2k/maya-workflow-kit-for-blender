"""In a real UI: File > Import opens the Maya file dialog (Blender file browser window) in the default
project's scenes folder, with Files of type + the Maya preset in the Options panel and the Current Project folder
list on the left; File > Export Selection with OBJ starts in the project's data folder (Maya file rule);
screenshots (ALLSET_GUI_SHOTS) to compare with Maya's File > Open dialog."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, setup, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def browser():
    """(window, area) of the open file browser, or (None, None)."""
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'FILE_BROWSER':
                return w, a
    return None, None


def shot(name):
    w, _a = browser()
    if SHOTS and w is not None:
        with bpy.context.temp_override(window=w):
            bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, name))


def close():
    w, a = browser()
    if w is not None:
        region = next(r for r in a.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=w, area=a, region=region):
            bpy.ops.file.cancel()


@step
def s_setup():
    setup()
    C["project"] = import_module(MODULE + ".operators.project")
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.create(kind='CUBE')
        bpy.ops.allset.menu_item('INVOKE_DEFAULT', item="File/Import...")


@step
def s_wait1():
    pass


@step
def s_import():
    w, a = browser()
    check("Import opens a file browser", a is not None)
    space = a.spaces.active
    op = space.active_operator
    check("it runs the Maya file dialog", op is not None and op.bl_idname == "ALLSET_OT_file_import")
    got = os.path.normcase(os.path.normpath(space.params.directory.decode()))
    want = os.path.normcase(os.path.normpath(C["project"].scenes_dir()))
    check(f"it starts in the default project's scenes folder ({got})", got == want)
    check("the default project is named default", os.path.basename(C["project"].current_root()) == "default")
    tools = next(r for r in a.regions if r.type == 'TOOLS')
    check("the bookmarks column is shown", tools.width > 1)


@step
def s_wait2():
    pass


@step
def s_import_shot():
    shot("gui_step102_import_dialog.png")
    close()


@step
def s_export():
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.file_export_selection('INVOKE_DEFAULT', export_type='OBJ')


@step
def s_wait3():
    pass


@step
def s_export_check():
    w, a = browser()
    space = a.spaces.active if a else None
    got = os.path.normcase(os.path.normpath(space.params.directory.decode())) if space else ""
    want = os.path.normcase(os.path.normpath(os.path.join(C["project"].current_root(), "data")))
    check(f"Export Selection as OBJ starts in the project's data folder ({got})", got == want)
    check("the file name gets the .obj extension", space is not None and space.params.filename.endswith(".obj"))


@step
def s_wait4():
    pass


@step
def s_export_shot():
    shot("gui_step102_export_selection_obj.png")
    close()


@step
def s_open():
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.open_scene('INVOKE_DEFAULT')


@step
def s_wait5():
    pass


@step
def s_wait6():
    pass


@step
def s_open_shot():
    w, a = browser()
    space = a.spaces.active if a else None
    got = os.path.normcase(os.path.normpath(space.params.directory.decode())) if space else ""
    want = os.path.normcase(os.path.normpath(C["project"].scenes_dir()))
    check(f"Open Scene starts in the project's scenes folder, not Documents ({got})", got == want)
    shot("gui_step102_open_dialog.png")
    close()


run()
