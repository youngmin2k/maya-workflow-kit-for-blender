# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Command Line and Help Line in Blender's status bar.

research/maya/ui_layout.md §4.12 (:290-293: language toggle, input/result
field, Script Editor button), §4.13 (:295-298: Help Line);
research/blender/api_limits.md #14 (:93-94). Design: docs/steps/step_7.md
「계획」 4. Python only: MEL is not supported (decision 5). ``maya.cmds`` is a
small look-alike (``cmds_shim``), importable as ``import maya.cmds as cmds`` in code run from the Command Line,
shelf buttons and the Script Editor only: those imports are rewritten to the kit's module before Blender's Run Script
runs the entry (``runner.prepare``, step 130).
"""


import bpy
from bpy.props import StringProperty

from .. import results
from . import runner, undo_text
from ..ui import own_draw

# --- state shown in the status bar --------------------------------------------------

_result = {"text": "", "error": False}


def show_result(text, error=False):
    """Put ``text`` in the Command Line result field (Maya's "// Result: ..." of a command) and redraw it."""
    _result["text"], _result["error"] = text, error
    wm = bpy.context.window_manager
    for window in wm.windows if wm else ():
        for area in window.screen.areas:
            if area.type == 'STATUSBAR':
                area.tag_redraw()
    try:
        from ..ui import status_line
        status_line.redraw_top_bars()
    except Exception:
        pass


def submit(text):
    """Run a command and keep its result for the result field."""
    res = runner.run(text)
    _result["text"], _result["error"] = res.text, res.error
    return res


def _on_command(self, context):
    text = self.allset_cmd
    if not text.strip():
        return
    self.allset_cmd = ""  # re-enters this callback with "" -> returns above
    submit(text)  # an error shows red in the result field
    # An operator called from a property update doesn't push an undo step
    # (measured in the GUI test), so push one: one command = one Ctrl+Z.
    bpy.ops.ed.undo_push(message=f"Command: {text[:40]}")
    undo_text.pushed(text.strip())        # Maya names a typed command's chunk by its text ("Undo: move -r 0 0 2")


class ALLSET_OT_command_line_exec(bpy.types.Operator):
    """Run a Python command (one undo step), like Maya's command line"""
    bl_idname = "allset.command_line_exec"
    bl_label = "Run Command"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    command: StringProperty(name="Command", options={'SKIP_SAVE'})

    def execute(self, context):
        res = submit(self.command)
        if res.error:
            self.report({'ERROR'}, res.text)
        elif res.text:
            results.result(self, res.text)
        return {'FINISHED'}


class ALLSET_OT_command_line_language(bpy.types.Operator):
    """Command language: Python. MEL is not supported in Blender"""
    bl_idname = "allset.command_line_language"
    bl_label = "Python"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        self.report({'WARNING'}, "MEL is not supported: the command line runs Python "
                                 "(cmds = a small maya.cmds subset; bpy, C, D as in the Python Console)")
        return {'FINISHED'}


class ALLSET_OT_script_editor(bpy.types.Operator):
    """Open the Maya Script Editor: history over input with MEL / Python tabs (ui/script_editor.py, step 105)"""
    bl_idname = "allset.script_editor"
    bl_label = "Script Editor"

    def execute(self, context):
        if context.window is None:
            return {'CANCELLED'}
        from ..ui import script_editor
        if script_editor.open_window(context) is None:
            self.report({'ERROR'}, "Could not open a new window")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_MT_command_history(bpy.types.Menu):
    """Recent commands: click to run again"""
    bl_idname = "ALLSET_MT_command_history"
    bl_label = "Recent Commands"

    def draw(self, context):
        layout = self.layout
        if not runner.history:
            layout.label(text="No commands yet")
        for cmd in reversed(runner.history):
            text = cmd if len(cmd) <= 60 else cmd[:57] + "..."
            layout.operator(ALLSET_OT_command_line_exec.bl_idname, text=text).command = cmd


# --- Help Line ---------------------------------------------------------------------------

# Maya shows the tool's help in the Help Line when a tool is active (ui_layout.md:295-298).
TOOL_HELP = {
    "builtin.select": "Select Tool: click or drag to select. Shift toggles, Ctrl deselects, Ctrl+Shift adds",
    "builtin.move": "Move Tool: drag the manipulator. Hold X/C/V to snap to grid/curve/point. Tap D to edit the pivot; click a vertex/edge/face; D again to finish",
    "builtin.rotate": "Rotate Tool: drag a ring to rotate. Hold J to snap rotation. Tap D to edit the pivot; D again to finish",
    "builtin.scale": "Scale Tool: drag a handle to scale, the centre scales uniformly",
    "builtin.transform": "Universal Manipulator: move, rotate and scale with one manipulator",
    "allset.multi_cut_tool": ("Multi-Cut: click edges / faces to place points, Enter or right-click to cut. "
                              "Ctrl+click: edge loop, Shift: snap step, Backspace: remove the last point"),
    "builtin.loop_cut": "Insert Edge Loop: click an edge to insert a loop, drag to slide it",
    "allset.insert_edge_loop_tool": "Insert Edge Loop: click an edge to insert a loop there, drag to slide it",
    "allset.offset_edge_loop_tool": "Offset Edge Loop: click an edge and drag to insert loops on both sides",
    "allset.slide_edge_tool": "Slide Edge: select edges, then middle-drag to slide them",
    "allset.quad_draw_tool": ("Quad Draw: click to place dots on the live surface, Shift+click to fill a quad, "
                              "drag to move, Shift+drag to relax, Ctrl+click: edge loop, Ctrl+Shift+click: delete, "
                              "Tab+drag: extend"),
    "allset.create_polygon_tool": ("Create Polygon: click to place points, Enter to complete, Backspace: remove the "
                                   "last point"),
    "allset.append_polygon_tool": ("Append to Polygon: click a border edge, then points, Enter to add the face, "
                                   "Backspace: remove the last point"),
    "allset.target_weld_tool": "Target Weld: drag a vertex or edge onto the target. Selected vertices are merged too",
    "allset.crease_tool": "Crease Tool: select edges or vertices, then middle-drag left to crease less, right for more",
}


def help_for_tool(idname):
    if idname.startswith("builtin.select"):  # select_box, select_lasso, ...
        return TOOL_HELP["builtin.select"]
    return TOOL_HELP.get(idname, "")


def help_text(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, TypeError):
        tool = None
    return help_for_tool(tool.idname) if tool else ""


# --- status bar --------------------------------------------------------------------------

# Maya 2022 puts the Help Line and the Command Line on one row, Help Line left (research/maya/ui_layout.md:
# 128-131, :290-298); widths from the factory window (_maya_ui_dump.json HelpLine 675 px, CommandLine 915 px
# at 1600 px) in UI units (20 px at effective scale 1.0).
HELP_UNITS = 33.75
COMMAND_UNITS = 45.75
# Inside the Command Line (research/maya/screens/16_four_view.png, 1600 px window): language button ~35 px, input
# ~335 px, result field ~485 px, Script Editor button. Step 161: the row is shared out as a fraction of the status bar
# like Maya's (the fixed UI units ran 1988 px wide at UI scale 1.25 in a 1600 px window, so the result field was drawn
# off the right edge and a command's result never showed).
INPUT_SHARE = 335 / 915
LANG_UNITS = 3.5          # "Python" button (Maya's "MEL" is 35 px; "Python" needs more)
MAYA_WINDOW_PX = 1600


def units_for(width_px, ui_scale):
    """(help, command, input) widths in UI units for a status bar ``width_px`` wide: Maya's 675 / 915 / 335 px of a
    1600 px window, scaled to the bar (at most Maya's sizes in UI units: a wide window keeps them)."""
    unit = 20.0 * max(ui_scale, 1e-3)
    f = min(1.0, width_px / unit / (MAYA_WINDOW_PX / 20.0))
    command = COMMAND_UNITS * f
    return HELP_UNITS * f, command, command * INPUT_SHARE


def row_units(context):
    """``units_for`` this status bar region (the window's width when there is no region)."""
    region = getattr(context, "region", None)
    scale = context.preferences.system.ui_scale
    width = region.width if region is not None and region.width > 1 else MAYA_WINDOW_PX * scale
    return units_for(width, scale)


def draw_help_line(layout, context):
    """Tool help, else Blender's mouse/key hints; reports and job progress after it (Maya's Help Line
    shows progress too)."""
    from ..ui import notices
    notices.remember_status_area(context.area, context.window)
    note = notices.current()   # a 「not in Blender」 notice of the menu item under the mouse (step 54)
    from ..ui import weight_numbers
    text = note or weight_numbers.help_note() or help_text(context)
    if text:
        layout.label(text=text, icon='ERROR' if note else 'INFO')
    else:
        layout.template_input_status()
    layout.template_reports_banner()
    # Blender lists playback as a running job ("Anim Player", #100); Maya's Help Line shows progress only for real
    # work (renders, bakes), so the jobs row is left out while the scene plays
    if not context.screen or not context.screen.is_animation_playing:
        layout.template_running_jobs()


def draw_command_line(layout, context):
    wm = context.window_manager
    _help, command, input_units = row_units(context)
    row = layout.row(align=True)
    sub = row.row(align=True)
    sub.ui_units_x = LANG_UNITS
    sub.operator(ALLSET_OT_command_line_language.bl_idname, text="Python")
    sub = row.row(align=True)
    sub.ui_units_x = input_units
    sub.prop(wm, "allset_cmd", text="", placeholder="Python  (cmds.polyCube(), C.object ...)")
    # a fixed result field: its text must not push the other buttons around
    sub = row.box().row()
    sub.ui_units_x = max(2.0, command - input_units - LANG_UNITS - 2.5)
    sub.alert = _result["error"]
    sub.label(text=_result["text"] or " ")
    row.menu(ALLSET_MT_command_history.bl_idname, text="", icon='RECOVER_LAST')
    row.operator(ALLSET_OT_script_editor.bl_idname, text="", icon='CONSOLE')


def draw_status_bar(self, context):
    """STATUSBAR_HT_header.draw while the kit is on: Help Line | Command Line, then Blender's
    scene statistics if there is room; Blender's own draw when both are off."""
    from .. import preferences
    try:
        prefs = preferences.get(context)
    except KeyError:
        prefs = None
    if prefs is None or not (prefs.show_help_line or prefs.show_command_line):
        return own_draw.original("STATUSBAR_HT_header", draw_status_bar)(self, context)
    layout = self.layout
    if prefs.show_help_line:
        row = layout.row()
        row.ui_units_x = row_units(context)[0]
        draw_help_line(row, context)
    if prefs.show_command_line:
        row = layout.row()
        row.ui_units_x = row_units(context)[1]
        draw_command_line(row, context)
    # No Blender status info (scene statistics, version, "Active object has non-uniform scale" / "negative scale"
    # warnings from template_status_info, #100): Maya's status row is Help Line + Command Line only; Maya shows
    # poly counts in the viewport HUD (Display > Heads Up Display).


classes = (ALLSET_OT_command_line_exec, ALLSET_OT_command_line_language,
           ALLSET_OT_script_editor, ALLSET_MT_command_history)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.allset_cmd = StringProperty(
        name="Command Line", description="Python command (Enter to run). MEL is not supported",
        options={'SKIP_SAVE'}, update=_on_command)
    # Only Blender's own status bar draw is swapped: other add-ons' appended items keep drawing (step 115).
    own_draw.swap("STATUSBAR_HT_header", draw_status_bar)
    undo_text.register()


def unregister():
    undo_text.unregister()
    own_draw.restore("STATUSBAR_HT_header", draw_status_bar)
    del bpy.types.WindowManager.allset_cmd
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    runner.reset()
    _result.update(text="", error=False)

