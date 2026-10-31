"""In a real UI: Maya top bar (menus, menu sets, Status Line), command line typing,
undo, Help Line, Script Editor window, tool switch from a menu; screenshots."""

import os
import sys
from importlib import import_module

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sim import MODULE, check, ev, run, step, setup, screenshot, tap, view3d, win, load_maya_layout  # noqa: E402

SHOTS = os.environ.get("ALLSET_GUI_SHOTS", "")
C = {}


def shot(name):
    if SHOTS:
        screenshot(os.path.join(SHOTS, name))


def prefs():
    return bpy.context.preferences.addons[MODULE].preferences


def redraw():
    for a in win().screen.areas:
        a.tag_redraw()


@step
def s_setup():
    setup()
    load_maya_layout()


@step
def s_wait():
    # --factory-startup: switching app template reloads factory preferences, so the
    # "Maya" keyconfig is not active any more (a user's saved prefs keep it).
    bpy.ops.allset.keymap_activate()
    C["cl"] = import_module(MODULE + ".command_line")
    C["sl"] = import_module(MODULE + ".ui.status_line")
    area, r = view3d()
    C["mid"] = (r.x + r.width // 2, r.y + r.height // 2)
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    redraw()


@step
def s_topbar():
    cls = bpy.types.TOPBAR_HT_upper_bar
    check("top bar draws the Maya menu bar", C["sl"].draw_upper_bar in cls.draw._draw_funcs)   # own draw swapped
    area, _r = view3d()
    # the Status Line lives in the Maya strip; the tool header row is Maya's panel toolbar
    check("main 3D View: the tool header row is the Maya panel toolbar", area.spaces.active.show_region_tool_header)
    shot("gui_step7_topbar_modeling.png")
    prefs().menu_set = 'riggingMenuSet'
    # The top bar is a global area (not in screen.areas): hovering it redraws it.
    ev('MOUSEMOVE', 'NOTHING', x=800, y=win().height - 12)


@step
def s_rigging_redraw():
    ev('MOUSEMOVE', 'NOTHING', x=820, y=win().height - 12)


@step
def s_rigging():
    shot("gui_step7_topbar_rigging.png")
    prefs().menu_set = 'modelingMenuSet'
    # Open a Maya menu as Blender would (same Menu class the menu bar uses).
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.call_menu(name="ALLSET_MT_mainMeshMenu")


@step
def s_menu_open():
    shot("gui_step7_mesh_menu.png")
    tap('ESC')
    # Type into the command line: click the field in the status bar (bottom row). The Command
    # Line is right of the Help Line (command_line.HELP_UNITS), its field after the language button.
    C["n0"] = len(bpy.data.objects)
    cl = import_module(MODULE + ".command_line")
    s = bpy.context.preferences.system.ui_scale
    k = min(s, win().width / cl.MAYA_WINDOW_PX)     # the row is shared out by the window width
    x = round(cl.HELP_UNITS * 20 * k + 60 * s + 150 * k)
    ev('MOUSEMOVE', 'NOTHING', x=x, y=12)  # hover first, so the field is the active button
    ev('LEFTMOUSE', 'PRESS', x=x, y=12)
    ev('LEFTMOUSE', 'RELEASE', x=x, y=12)


@step
def s_type():
    for ch in "cmds.polyCube(w=200, h=200, d=200)":
        ev('TEXTINPUT', 'PRESS', unicode=ch)
    ev('RET', 'PRESS')
    ev('RET', 'RELEASE')


@step
def s_typed():
    res = C["cl"]._result
    check(f"typed command ran: result {res['text']!r}", res["text"].startswith("# Result: ['pCube1'"))
    check("cube created by cmds.polyCube", "pCube1" in bpy.data.objects)
    check("command field cleared", bpy.context.window_manager.allset_cmd == "")
    redraw()


@step
def s_cmd_shot():
    shot("gui_step7_command_line.png")
    ev('MOUSEMOVE', 'NOTHING', x=C["mid"][0], y=C["mid"][1])
    ev('Z', 'PRESS', ctrl=True)
    ev('Z', 'RELEASE', ctrl=True)


@step
def s_undo():
    check("Ctrl+Z undoes the whole command (one step)", "pCube1" not in bpy.data.objects)
    # Error result: red field.
    bpy.context.window_manager.allset_cmd = "polyCube -w 2;"
    redraw()


@step
def s_error_shot():
    res = C["cl"]._result
    check("MEL input -> error with Python hint", res["error"] and "cmds.polyCube(w=2)" in res["text"])
    shot("gui_step7_mel_error.png")
    # Holding X lights the grid snap button in the Status Line.
    bpy.ops.mesh.primitive_cube_add()
    with bpy.context.temp_override(window=win()):
        bpy.ops.wm.tool_set_by_id(name="builtin.move", space_type='VIEW_3D')
    ev('X', 'PRESS')


@step
def s_hold():
    ts = bpy.context.scene.tool_settings
    check("X held: grid snap on (Status Line button lit)", C["sl"].snap_on(ts, "GRID"))
    redraw()


@step
def s_hold_shot():
    shot("gui_step7_hold_x.png")
    ev('X', 'RELEASE')


@step
def s_release():
    ts = bpy.context.scene.tool_settings
    check("X released: grid snap off again", not C["sl"].snap_on(ts, "GRID"))
    check("Help Line text for the Move tool", "Move Tool" in C["cl"].help_text(bpy.context))
    # Tool switch from a Maya menu item (fails headless: no tool keymaps in -b).
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.menu_tool(tool="allset.multi_cut_tool", edit=True)
    tool = bpy.context.workspace.tools.from_space_view3d_mode('EDIT_MESH', create=False)
    check("Mesh Tools > Multi-Cut: edit mode + Multi-Cut tool",
          bpy.context.mode == 'EDIT_MESH' and tool is not None and tool.idname == "allset.multi_cut_tool")
    bpy.ops.object.mode_set(mode='OBJECT')
    # A "v3d" item: runs in the 3D View (Display > Grid).
    v3d = view3d()[0].spaces.active
    grid = import_module(MODULE + ".ui.maya_grid")
    C["grid"] = grid.visible(v3d)
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.menu_run(op="allset.toggle_grid", props='{}')
    check("Display > Grid toggles the viewport grid (Maya grid)", grid.visible(v3d) != C["grid"])
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.menu_run(op="allset.toggle_grid", props='{}')
    C["windows"] = len(bpy.context.window_manager.windows)
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.script_editor()


@step
def s_script_editor():
    wins = bpy.context.window_manager.windows
    check("Script Editor opens a new window", len(wins) == C["windows"] + 1)
    if len(wins) > C["windows"]:
        new = wins[len(wins) - 1]
        # the Maya Script Editor = history (Info) over input (Text Editor)
        check("new window is the Script Editor (history over input)",
              sorted(a.type for a in new.screen.areas) == ['INFO', 'TEXT_EDITOR'])
        if SHOTS:
            with bpy.context.temp_override(window=new):
                bpy.ops.screen.screenshot(filepath=os.path.join(SHOTS, "gui_step7_script_editor.png"))
        with bpy.context.temp_override(window=new):
            bpy.ops.wm.window_close()
    # Tool Settings button: the active tool's settings as a popup.
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.editor_toggle(editor="TOOL_SETTINGS")


@step
def s_tool_settings():
    shot("gui_step7_tool_settings.png")
    # the Tool Settings dock; toggle again to close it
    with bpy.context.temp_override(window=win()):
        bpy.ops.allset.editor_toggle(editor="TOOL_SETTINGS")


run()
