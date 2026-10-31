"""The welcome dialog's body was cut at 125 % UI scale ("the Maya colou..."): fixed lines wider than the
room left of the icon. welcome.wrap breaks the paragraphs by blf width. Checked on the wrapped lines and
on a screenshot of the open dialog (look at it: ALLSET_GUI_SHOTS)."""

import os
import sys
import tempfile
from importlib import import_module

import addon_utils
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, screenshot, tap, view3d, win  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


@step
def s_setup():
    tap('ESC')
    addon_utils.enable(MODULE, default_set=True)      # plain Blender: the dialog's own case
    bpy.context.preferences.view.show_tooltips = False


@step
def s_open():
    _area, r = view3d()
    ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + int(r.height * 0.62))
    with bpy.context.temp_override(window=win()):
        C["op"] = bpy.ops.allset.welcome('INVOKE_DEFAULT')
    check("welcome dialog opens", C["op"] == {'RUNNING_MODAL'})


@step
def s_wait():
    pass


@step
def s_check():
    w = import_module(MODULE + ".welcome")
    prefs = bpy.context.preferences
    scale = prefs.system.ui_scale
    size = prefs.ui_styles[0].widget.points * scale
    room = w.text_room() * scale
    lines = [ln for p in w.PARAGRAPHS for ln in w.wrap(p, room, size)]
    widest = max(w.text_width(ln, size) for ln in lines)
    check(f"every body line fits the room left of the icon ({widest:.0f} / {room:.0f} px, {len(lines)} lines, "
          f"scale {scale})", widest <= room)
    words = " ".join(lines).split()
    check("no word lost by wrapping", words == " ".join(w.PARAGRAPHS).split())
    screenshot(os.path.join(SHOTS or tempfile.gettempdir(), "gui_step124_welcome.png"))


run()
