# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Script Editor window.

Maya 2022:
menu bar File / Edit / History / Command / Tabs / Help, an icon row, the history pane (echo of commands and results)
over the input pane with tabs MEL / Python (+). Ctrl+Enter executes and keeps the input; the Execute button / numpad
Enter executes and clears it.

Blender: one window split into history = Info editor (Blender's report log: every operator echoed as Python, the
kit's command echo and results as reports) over input = Text Editor showing the text "Python" or "MEL". The window is
marked (window pointer); in it the Info header draws the Maya menu bar + icon row and the Text header the tabs. The
Python tab runs through the command line runner (``command_line/runner.py``: ``cmds`` subset, ``bpy``, C, D; the
value of a last expression is the result); the MEL tab gives Maya's warning (no MEL).

History menu: Maya's scriptEditorInfo options are add-on preferences (``se_*``) drawn as check / radio
items; ``runner.history_lines`` applies them to what a run writes into the history, ``runner.echo_command`` writes
Echo All Commands lines (``allset.script_echo``).
"""

import bpy
from bpy.props import BoolProperty, StringProperty

from .. import undo_steps

_WINDOWS = set()
LANG_PROP = "allset_script_lang"        # "MEL" / "Python" on the kit's script texts
TABS = (("MEL", "MEL"), ("Python", "Python"))     # Maya's two default tabs, Python current (factory: MEL first)


def mark(window):
    _WINDOWS.add(window.as_pointer())


def is_script_editor(context):
    window = context.window
    return window is not None and window.as_pointer() in _WINDOWS


def script_texts():
    return [t for t in bpy.data.texts if t.get(LANG_PROP)]


def ensure_texts():
    """The MEL and Python tabs (texts marked with their language); returns the Python one."""
    out = {}
    for name, lang in TABS:
        t = next((x for x in script_texts() if x.get(LANG_PROP) == lang and x.name.startswith(name)), None)
        if t is None:
            t = bpy.data.texts.new(name)
            t[LANG_PROP] = lang
        out[lang] = t
    return out["Python"]


def areas(window):
    """(history Info area, input Text area) of a kit Script Editor window."""
    info = next((a for a in window.screen.areas if a.type == 'INFO'), None)
    text = next((a for a in window.screen.areas if a.type == 'TEXT_EDITOR'), None)
    return info, text


def open_window(context):
    """A new window: Info (history) over a Text Editor (input) on the Python tab."""
    from ..operators import menu_extras
    area = max(context.window.screen.areas, key=lambda a: a.width * a.height, default=None)
    if area is None:
        return None
    window = menu_extras.open_window(context, area, "script_editor")
    if window is None:
        return None
    target = window.screen.areas[0]
    target.type = 'TEXT_EDITOR'
    target.spaces.active.text = ensure_texts()
    target.spaces.active.show_line_numbers = True
    with context.temp_override(window=window, screen=window.screen, area=target):
        bpy.ops.screen.area_split(direction='HORIZONTAL', factor=0.55)
    top = next((a for a in window.screen.areas if a != target), None)
    if top is not None:
        top.type = 'INFO'      # a horizontal split gives the new area the top part
    mark(window)
    return window


def selected_text(text):
    """The text's selection (Text Editor), "" without one."""
    a = (text.current_line_index, text.current_character)
    b = (text.select_end_line_index, text.select_end_character)
    if a == b:
        return ""
    (l0, c0), (l1, c1) = sorted((a, b))
    lines = [ln.body for ln in text.lines]
    if l0 == l1:
        return lines[l0][c0:c1]
    return "\n".join([lines[l0][c0:]] + lines[l0 + 1:l1] + [lines[l1][:c1]])


def run_text(text, code):
    """(echo lines, result Result) of running ``code`` from a script tab."""
    from ..command_line import runner
    if text.get(LANG_PROP) == "MEL":
        return code, runner.Result("// Error: MEL is not supported in Blender: use the Python tab (cmds = a maya.cmds "
                                   "subset, bpy, C, D).", True)
    return code, runner.run(code)


# Blender report type of each history line kind (runner.KINDS); the echo / output / results are INFO like Blender's
# own Python console echo (the Script Editor keeps its INFO reports).
REPORT_TYPES = {"WARNING": 'WARNING', "ERROR": 'ERROR', "TRACE": 'ERROR'}


def write_history(op, echo, res, lang="Python"):
    """Write a run into the history pane (Blender's report log, listed by the Info editor) after the History menu
    options (Line numbers / Stack Trace / Suppress ... / History Output, ``runner.history_lines``)."""
    from ..command_line import runner
    lines = runner.history_lines(echo, res, lang)
    for kind, line in lines:
        if kind in REPORT_TYPES:
            op.report({REPORT_TYPES[kind]}, line)
        else:
            op.report({'INFO'}, line)
    return lines


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_script_run(bpy.types.Operator):
    """Maya Script Editor: execute the selection, else the whole tab (Ctrl+Enter keeps the input, Execute / numpad
    Enter clears it)"""
    bl_idname = "allset.script_run"
    bl_label = "Execute"
    bl_options = {'REGISTER', 'UNDO'}

    clear: BoolProperty(name="Clear Input", description="Clear the input after running the whole tab (Maya's "
                        "Execute button / numpad Enter)", options={'SKIP_SAVE'})

    def invoke(self, context, event):
        if not is_script_editor(context):
            return {'PASS_THROUGH'}
        return self.execute(context)

    def execute(self, context):
        text = getattr(context.space_data, "text", None) if context.space_data else None
        if text is None and context.window is not None:
            _info, area = areas(context.window)
            text = area.spaces.active.text if area is not None else None
        if text is None:
            return {'CANCELLED'}
        part = selected_text(text)
        code = part or text.as_string()
        if not code.strip():
            return {'CANCELLED'}
        name, loads = text.name, _carry["loads"]
        echo, res = run_text(text, code)
        write_history(self, echo, res, text.get(LANG_PROP) or "Python")
        if _carry["loads"] != loads:      # the script loaded a file (cmds.file): the old Text is gone, use its copy
            text = bpy.data.texts.get(name)
        if self.clear and not part and not res.error and text is not None:
            text.clear()
        return {'FINISHED'}


class ALLSET_OT_script_echo(bpy.types.Operator):
    """Maya History > Echo All Commands: one command line in the Script Editor history"""
    bl_idname = "allset.script_echo"
    bl_label = "Echo Command"
    bl_options = {'INTERNAL'}

    text: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        # OPERATOR type: the Info editor lists it like Blender's own operator echo; no status-bar banner (Blender
        # shows INFO / WARNING / ERROR reports there only).
        self.report({'OPERATOR'}, self.text)
        return {'FINISHED'}


class ALLSET_OT_script_clear(bpy.types.Operator):
    """Maya Script Editor Edit > Clear History / Clear Input / Clear All"""
    bl_idname = "allset.script_clear"
    bl_label = "Clear"
    bl_options = {'REGISTER'}

    what: bpy.props.EnumProperty(items=(("HISTORY", "Clear History", ""), ("INPUT", "Clear Input", ""),
                                        ("ALL", "Clear All", "")), name="Clear", options={'SKIP_SAVE'})

    def execute(self, context):
        window = context.window
        info, text_area = areas(window) if window is not None else (None, None)
        if self.what in {"HISTORY", "ALL"} and info is not None:
            region = next(r for r in info.regions if r.type == 'WINDOW')
            with context.temp_override(window=window, area=info, region=region):
                bpy.ops.info.select_all(action='SELECT')
                bpy.ops.info.report_delete()
        if self.what in {"INPUT", "ALL"}:
            space = text_area.spaces.active if text_area is not None else context.space_data
            text = getattr(space, "text", None)
            if text is not None:
                text.clear()
        return {'FINISHED'}


class ALLSET_OT_script_tab(bpy.types.Operator):
    """Maya Script Editor tab: show this script (or make a new Python tab)"""
    bl_idname = "allset.script_tab"
    bl_label = "Script Tab"

    name: StringProperty(options={'SKIP_SAVE'})
    new: BoolProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        _info, area = areas(context.window) if context.window is not None else (None, None)
        space = area.spaces.active if area is not None else context.space_data
        if self.new:
            t = bpy.data.texts.new("Python")
            t[LANG_PROP] = "Python"
        else:
            t = bpy.data.texts.get(self.name)
        if t is None or space is None or space.type != 'TEXT_EDITOR':
            return {'CANCELLED'}
        space.text = t
        return {'FINISHED'}


# --- headers -------------------------------------------------------------------------------------------------

ICONS = (("FILEBROWSER", "text.open", {}, "Open a script"), ("FILE_TICK", "text.save_as", {}, "Save the script"),
         "|",
         ("TRASH", "allset.script_clear", {"what": "HISTORY"}, "Clear history"),
         ("X", "allset.script_clear", {"what": "INPUT"}, "Clear input"),
         ("CANCEL", "allset.script_clear", {"what": "ALL"}, "Clear all"),
         "|",
         ("PLAY", "allset.script_run", {"clear": True}, "Execute all (clears the input)"),
         ("FRAME_NEXT", "allset.script_run", {}, "Execute (keeps the input)"))


def draw_icons(layout):
    row = layout.row(align=True)
    for it in ICONS:
        if it == "|":
            row.separator()
            row = layout.row(align=True)
            continue
        icon, idname, props, _tip = it
        op = row.operator(idname, text="", icon=icon)
        for k, v in props.items():
            setattr(op, k, v)


def _info_header(self, context):
    if not is_script_editor(context):
        return _orig["info"](self, context)
    from . import editor_chrome
    layout = self.layout
    layout.template_header()
    editor_chrome.draw_menus(layout, context, "Script Editor")
    layout.separator()
    draw_icons(layout)


def _text_header(self, context):
    if not is_script_editor(context):
        return _orig["text"](self, context)
    layout = self.layout
    space = context.space_data
    layout.template_header()
    row = layout.row(align=True)
    for t in script_texts():
        op = row.operator(ALLSET_OT_script_tab.bl_idname, text=t.name,
                          icon='CONSOLE' if t.get(LANG_PROP) == "MEL" else 'SCRIPT', depress=space.text == t)
        op.name = t.name
    row.operator(ALLSET_OT_script_tab.bl_idname, text="", icon='ADD').new = True
    layout.separator_spacer()
    layout.operator(ALLSET_OT_script_run.bl_idname, text="Execute", icon='PLAY').clear = True


# --- the tabs survive File > New / Open (Maya keeps the Script Editor's input; ``cmds.file`` too) ----------

_carry = {"texts": [], "shown": {}, "loads": 0}


@bpy.app.handlers.persistent
def _load_pre(*_args):
    _carry["texts"] = [(t.name, t[LANG_PROP], t.as_string()) for t in script_texts()]
    shown = {}
    for wm in bpy.data.window_managers:
        for window in wm.windows:
            if window.as_pointer() in _WINDOWS:
                _info, area = areas(window)
                text = area.spaces.active.text if area is not None else None
                shown[window.as_pointer()] = text.name if text is not None else None
    _carry["shown"] = shown


@bpy.app.handlers.persistent
def _load_post(*_args):
    _carry["loads"] += 1
    made = {}
    for name, lang, body in _carry["texts"]:
        t = bpy.data.texts.get(name)
        if t is None or t.get(LANG_PROP) != lang:
            t = bpy.data.texts.new(name)
            t[LANG_PROP] = lang
            t.write(body)
        made[name] = t
    for wm in bpy.data.window_managers:
        for window in wm.windows:
            name = _carry["shown"].get(window.as_pointer())
            if name in made:
                _info, area = areas(window)
                if area is not None:
                    area.spaces.active.text = made[name]
    _carry["texts"], _carry["shown"] = [], {}


_orig = {}
HEADERS = (("info", "INFO_HT_header", _info_header), ("text", "TEXT_HT_header", _text_header))

classes = (ALLSET_OT_script_run, ALLSET_OT_script_echo, ALLSET_OT_script_clear, ALLSET_OT_script_tab)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for key, name, fn in HEADERS:
        funcs = getattr(bpy.types, name)._dyn_ui_initialize()
        _orig[key] = funcs[0]
        funcs[0] = fn
    bpy.app.handlers.load_pre.append(_load_pre)
    bpy.app.handlers.load_post.append(_load_post)


def unregister():
    for handlers, fn in ((bpy.app.handlers.load_pre, _load_pre), (bpy.app.handlers.load_post, _load_post)):
        if fn in handlers:
            handlers.remove(fn)
    for key, name, _fn in HEADERS:
        if key in _orig:
            getattr(bpy.types, name)._dyn_ui_initialize()[0] = _orig.pop(key)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _WINDOWS.clear()
