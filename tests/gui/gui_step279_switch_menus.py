"""#198 #199: smoke in a real UI: enable the kit, "Make Blender feel like Maya" (welcome opt-in with the
Maya layout), open the Maya File menu (its draw runs without a Python error), switch back to Blender: the top bar,
the toolbar tools and the workspace are Blender's again, only the always-on part of the kit stays registered.

First the same with one Maya-mode module failing to register (#198 / #199 on the user's machine): Maya mode stays
off, nothing half-registered is left, and the next opt-in works. Part of the release smoke matrix
(``python tools/smoke_matrix.py``, every supported Blender minor).
"""

import os
import sys
import traceback
from importlib import import_module

import addon_utils
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, run, step, tap, win, _keep_ui_scale  # noqa: E402

GUI_TIMEOUT = 240
C = {"draw_calls": 0, "draw_errors": []}


def mod(name):
    return import_module(f"{MODULE}.{name}")


def allset_types():
    return {n for n in dir(bpy.types) if n.startswith("ALLSET_")}


def topbar_draws():
    cls = bpy.types.TOPBAR_HT_upper_bar
    return [f"{getattr(f, '__module__', '?')}.{getattr(f, '__qualname__', '?')}"
            for f in getattr(cls.draw, "_draw_funcs", [cls.draw])]


def kit_tools():
    out = []
    for mode, items in bpy.types.VIEW3D_PT_tools_active._tools.items():
        for item in items:
            for t in (item if isinstance(item, tuple) else (item,)):
                if t is not None and not callable(t) and getattr(t, "idname", "").startswith("allset"):
                    out.append(f"{mode}:{t.idname}")
    return out


def blender_again(what):
    sw = mod("switch")
    check(f"{what}: Maya mode off ({sw.is_on()}, registered {sw._registered[0]})",
          not sw.is_on() and not sw._registered[0] and not sw._mode_done)
    check(f"{what}: top bar = Blender's ({topbar_draws()})", topbar_draws() == C["topbar"])
    extra = allset_types() - C["core_types"]
    check(f"{what}: only the always-on kit types left ({len(extra)} extra, e.g. {sorted(extra)[:4]})", not extra)
    check(f"{what}: no kit tools in the toolbar ({kit_tools()[:4]})", not kit_tools())
    check(f"{what}: workspace not a Maya one ({win().workspace.name})", not sw.is_maya_workspace(win().workspace))


def opt_in():
    mod("welcome").opt_in(open_layout=True)


def wait():
    pass


def watch_file_menu_draw():
    cls = bpy.types.ALLSET_MT_mainFileMenu
    real = cls.draw

    def draw(self, context):
        C["draw_calls"] += 1
        try:
            real(self, context)
        except Exception:
            C["draw_errors"].append(traceback.format_exc())
            raise
    cls.draw = draw
    C["real_draw"] = (cls, real)


@step
def s_setup():
    tap('ESC')
    _keep_ui_scale()
    addon_utils.enable(MODULE, default_set=True)
    C["topbar"] = topbar_draws()           # Blender's draw + the always-on Maya | Blender switch
    C["core_types"] = allset_types()
    check(f"enabled: Maya mode off, {len(C['core_types'])} always-on kit types", not mod("switch").is_on())
    # one Maya mode module fails (dock_tabs: after the Status Line swapped the top bar, before the tear-off op)
    dock_tabs = mod("ui.dock_tabs")
    C["dock_tabs_register"] = dock_tabs.register

    def boom():
        raise RuntimeError("injected register failure")
    dock_tabs.register = boom
    opt_in()


for _ in range(4):
    step(wait)


@step
def s_failed():
    mod("ui.dock_tabs").register = C.pop("dock_tabs_register")
    sw = mod("switch")
    check(f"a failed start is reported ({sw.last_error[0]})", bool(sw.last_error[0]))
    blender_again("after a failed start")
    opt_in()


for _ in range(8):
    step(wait)


@step
def s_maya_on():
    sw = mod("switch")
    check(f"Maya mode on ({sw.is_on()}, {sw._registered[0]})", sw.is_on() and sw._registered[0])
    check("tear-off operator registered", "ALLSET_OT_menu_tear_off" in allset_types())
    check("Maya top bar drawn", topbar_draws() != C["topbar"])
    check(f"Maya layout ({win().workspace.name})", sw.is_maya_workspace(win().workspace))
    watch_file_menu_draw()
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    with bpy.context.temp_override(window=win(), area=area):
        bpy.ops.wm.call_menu(name="ALLSET_MT_mainFileMenu")


@step
def s_menu_drawn():
    check(f"File menu drawn ({C['draw_calls']} draws)", C["draw_calls"] > 0)
    check("File menu draw: no Python error" + (f" ({C['draw_errors'][0][-300:]})" if C["draw_errors"] else ""),
          not C["draw_errors"])
    cls, real = C.pop("real_draw")
    cls.draw = real
    tap('ESC')


@step
def s_off():
    mod("switch").set_mode(False, layout=True)


for _ in range(4):
    step(wait)


@step
def s_blender():
    blender_again("after switching back")


run()
