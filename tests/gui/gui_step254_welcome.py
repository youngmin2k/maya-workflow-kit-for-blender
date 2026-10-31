"""#170: the welcome dialog opened at the main window's last pointer position. After installing from
Edit > Preferences that was the menu bar, so the dialog sat over File / Edit / ... and swallowed every click there
("top menus not responding" on 5.2.2; same in 4.5). Now it waits (allset.welcome_wait) until the
pointer moves inside the main window clear of the menu bar, and opens there. Look at the shots: ALLSET_GUI_SHOTS."""

import os
import sys
import tempfile
from importlib import import_module

import addon_utils
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, screenshot, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "") or tempfile.gettempdir()
C = {}


def _prefs():
    return import_module(MODULE + ".preferences").get()


def _waiting():
    return any(op.bl_idname == "ALLSET_OT_welcome_wait" for op in win().modal_operators)


@step
def s_setup():
    tap('ESC')
    addon_utils.enable(MODULE, default_set=True)      # plain Blender (the dialog's own case)
    bpy.context.preferences.view.show_tooltips = False
    p = _prefs()
    p.welcome_done = False
    p.welcome_shown = 0
    check("Maya mode off (the welcome case)", not p.maya_mode)


@step
def s_pointer_on_menu_bar():
    w = win()
    ev('MOUSEMOVE', 'NOTHING', x=90, y=w.height - 12)      # where Edit > Preferences was clicked


@step
def s_show():
    import_module(MODULE + ".welcome")._show_welcome()    # what the register timer runs
    check("the kit waits for the pointer instead of opening the dialog", _waiting())


@step
def s_moves_on_bar():
    w = win()
    for x in (60, 120, 180):
        ev('MOUSEMOVE', 'NOTHING', x=x, y=w.height - 12)


@step
def s_check_no_dialog():
    check("pointer on the menu bar: no dialog (welcome not shown yet)", not _prefs().welcome_shown and _waiting())


@step
def s_press_file():
    ev('MOUSEMOVE', 'NOTHING', x=50, y=win().height - 12)


@step
def s_press():
    ev('LEFTMOUSE', 'PRESS')


@step
def s_release():
    ev('LEFTMOUSE', 'RELEASE')


@step
def s_wait_menu():
    pass


@step
def s_shot_menu():
    screenshot(os.path.join(SHOTS, "gui_step254_file_menu.png"))
    check("File clicked with no dialog in the way", not _prefs().welcome_shown)


@step
def s_close_menu():
    tap('ESC')


@step
def s_into_view():
    _a, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + int(r.height * 0.2))
    C["at"] = (r.x + r.width // 2, r.y + int(r.height * 0.2))


@step
def s_opened():
    # the dialog counts its showings (welcome_done only once confirmed or shown WELCOME_SHOWS times)
    check("pointer in the viewport: the dialog opens (welcome shown)", _prefs().welcome_shown == 1)
    check("the wait operator ended", not _waiting())


@step
def s_wait_draw():
    pass


@step
def s_shot_dialog():
    screenshot(os.path.join(SHOTS, "gui_step254_dialog.png"))
    print("pointer at", C["at"], "window", win().width, win().height, flush=True)


@step
def s_esc():
    tap('ESC')


run()
