# SPDX-License-Identifier: GPL-3.0-or-later
"""The opt-in: nothing changes until the user asks for Maya.

Part of CORE (registered whenever the extension is enabled, also in Blender mode). Enabling the extension only adds
the Maya | Blender switch, an Edit menu item, Ctrl+Alt+Shift+M and, once in a GUI session, this welcome dialog. Its
confirm button "Make Blender feel like Maya" (also in the add-on preferences) turns on Maya mode and Make Blender
Maya (``first_start.make``: start in the Maya layout, the layout shown now). Cancelling changes nothing. Blender's
preferences are never written.

Not in background runs; GUI tests and tools set ``ALLSET_NO_WELCOME=1`` (the dialog would eat simulated events).
"""

import os

import bpy

from . import i18n, preferences

# Square art made by tools/make_splash.py (icons are square; the 2:1 splash would letterbox).
WELCOME_IMAGE = os.path.join(os.path.dirname(__file__), "welcome.png")
_previews = None


def _splash_icon():
    global _previews
    if not os.path.isfile(WELCOME_IMAGE):
        return 0
    if _previews is None:
        import bpy.utils.previews
        _previews = bpy.utils.previews.new()
    if "splash" not in _previews:
        _previews.load("splash", WELCOME_IMAGE, 'IMAGE')
    return _previews["splash"].icon_id


def _window():
    wm = bpy.context.window_manager
    return wm.windows[0] if wm and wm.windows else None


def opt_in(open_layout=True):
    """Everything "Make Blender feel like Maya" does. Runs from a timer (switching registers the Maya mode
    modules, which an operator of theirs must not do while it runs)."""
    from . import switch
    switch.set_mode(True, layout=False)
    if not switch._registered[0]:     # Maya mode could not start (reported, rolled back): nothing more to do
        return
    from . import first_start
    first_start.make(bpy.context, open_layout=False)
    if open_layout:
        # an untouched new file: a new Maya scene; the user's file: the layout workspace appended, data kept
        first_start.show_layout(_window())


# Body text, wrapped to the room left of the icon: fixed lines were cut ("the Maya colou...") at 125 %
# UI scale.
PARAGRAPHS = (
    i18n.mark("The whole Maya workflow in Blender, in one install."),
    i18n.mark("Nothing has changed yet. Make Blender feel like Maya turns on the Maya-style keys: Alt+mouse, QWER, "
              "Space hotbox, marking menus; the Maya layout, menus, Channel Box and shelf."),
    i18n.mark("Your Blender preferences are never changed: the Maya | Blender switch at the top right or "
              "Ctrl+Alt+Shift+M goes back to plain Blender at any time."),
    # the kit may not raise Blender's undo depth itself
    i18n.mark("Tip: Maya's undo is unlimited, Blender keeps 32 steps by default. Raise Edit > Preferences > System > "
              "Undo Steps to 256 if you like Maya's long undo."),
)
WELCOME_SHOWS = 2       # starts the welcome dialog opens on until it is confirmed
DIALOG_WIDTH = 640      # unscaled px
ICON_SCALE = 7.0        # template_icon scale = 20 px units
ICON_FACTOR = (ICON_SCALE * 20 + 16) / DIALOG_WIDTH     # icon column share of the split
TEXT_PAD = 40           # dialog margins + label padding, unscaled px (generous: a cut word is worse than a short line)


def text_room(with_icon=True):
    """Unscaled px a body line may take."""
    return DIALOG_WIDTH * ((1.0 - ICON_FACTOR) if with_icon else 1.0) - TEXT_PAD


def text_width(text, size):
    import blf
    blf.size(0, size)
    return blf.dimensions(0, text)[0]


def wrap(text, width, size, measure=text_width):
    """Words of ``text`` in lines no wider than ``width`` px at font ``size`` (a word longer than a line stays whole)."""
    if any(i18n.width(ch) == 2 for ch in text):    # Chinese / Japanese: a line may break between any two characters
        words, sep = [w for w in i18n.split_points(text) if w.strip()], ""
    else:
        words, sep = text.split(), " "
    lines, cur = [], ""
    for word in words:
        cand = f"{cur}{sep}{word}" if cur else word
        if cur and measure(cand, size) > width:
            lines.append(cur.rstrip())
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur.rstrip())
    return lines


class ALLSET_OT_welcome(bpy.types.Operator):
    """Turn on the Maya-style keys, layout and menus (asks first). Blender's preferences are not changed;
    Ctrl+Alt+Shift+M or the Maya / Blender switch turns it off again"""
    bl_idname = "allset.welcome"
    bl_label = "Make Blender feel like Maya"
    bl_options = {'INTERNAL'}

    open_layout: bpy.props.BoolProperty(name="Open Maya Layout", default=True, options={'SKIP_SAVE'})

    def invoke(self, context, event):
        # #177: a dialog closed without the confirm button (Cancel, Esc and moving away all reach Blender's
        # popup cancel alike) opens once more at the next start; after WELCOME_SHOWS it stays closed (a
        # dismissed dialog left users in Blender mode without knowing, "Alt navigation doesn't work").
        prefs = preferences.get(context)
        prefs.welcome_shown += 1
        if prefs.welcome_shown >= WELCOME_SHOWS:
            prefs.welcome_done = True
        return context.window_manager.invoke_props_dialog(
            self, width=DIALOG_WIDTH, title=i18n.iface("Welcome to Maya Workflow Kit"),
            confirm_text=i18n.iface("Make Blender feel like Maya"))

    def draw(self, context):
        icon = _splash_icon()
        if icon:    # a plain row halves the dialog: give the icon only its own width
            row = self.layout.split(factor=ICON_FACTOR)
            row.template_icon(icon_value=icon, scale=ICON_SCALE)
        else:
            row = self.layout.row()
        col = row.column()
        col.label(text="Maya Workflow Kit")
        scale = context.preferences.system.ui_scale or 1.0      # 0 in background
        size = context.preferences.ui_styles[0].widget.points * scale
        width = text_room(bool(icon)) * scale
        paras = PARAGRAPHS
        emulate = preferences.emulate_hint(context)
        if emulate:
            paras = paras + (emulate,)
        for k, para in enumerate(paras):
            if k:
                col.separator()
            for line in wrap(i18n.iface(para), width, size):      # translated before wrapping
                col.label(text=line, translate=False)

    def execute(self, context):
        preferences.get(context).welcome_done = True
        open_layout = self.open_layout
        bpy.app.timers.register(lambda: opt_in(open_layout), first_interval=0.0)
        return {'FINISHED'}


# Where the dialog may open (#170). Blender opens a props dialog at the window's last pointer position, clamped
# into the window. Installing from Edit > Preferences leaves the main window's pointer on the menu bar, so the dialog
# opened over File / Edit / ... and swallowed every click there, often hidden behind the Preferences window: "the top
# menus don't respond" (GUI 4.5.4 / 5.2.2). So the kit waits until the pointer moves inside the main
# window far enough below its top for the whole dialog, and opens it there.
DIALOG_ROOM_PX = 420      # unscaled px kept above the pointer (the dialog is ~378 px tall at UI scale 1.25 = ~300 unscaled)


def spot_ok(window, x, y, ui_scale):
    """The pointer (window px, bottom-left origin) is a place the dialog may open: in the window, below the top bar by
    the dialog's height, above the status bar."""
    return 0 <= x < window.width and 30 * ui_scale <= y <= window.height - DIALOG_ROOM_PX * ui_scale


def _wanted():
    try:
        prefs = preferences.get()
    except KeyError:
        return False
    return not (prefs.welcome_done or prefs.maya_mode)


class ALLSET_OT_welcome_wait(bpy.types.Operator):
    """Open the welcome dialog once the pointer is in the main window, clear of its menu bar"""
    bl_idname = "allset.welcome_wait"
    bl_label = "Welcome (wait for the pointer)"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        self._win = context.window.as_pointer()
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if not _wanted():
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type != 'MOUSEMOVE' or context.window is None or context.window.as_pointer() != self._win:
            return {'PASS_THROUGH'}
        win = context.window
        x, y = event.mouse_x, event.mouse_y
        if not spot_ok(win, x, y, context.preferences.system.ui_scale or 1.0):
            return {'PASS_THROUGH'}
        ptr = self._win

        def show():
            from . import live_refs
            w = live_refs.window(ptr)
            if w is not None and _wanted():
                with bpy.context.temp_override(window=w, screen=w.screen):
                    bpy.ops.allset.welcome('INVOKE_DEFAULT')
            return None
        bpy.app.timers.register(show, first_interval=0.0)    # not from inside this modal's own event
        return {'FINISHED', 'PASS_THROUGH'}


def _show_welcome():
    if not _wanted():
        return None
    win = _window()
    if win is None:
        return 0.5
    with bpy.context.temp_override(window=win, screen=win.screen):
        bpy.ops.allset.welcome_wait('INVOKE_DEFAULT')
    return None


classes = (ALLSET_OT_welcome, ALLSET_OT_welcome_wait)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if not bpy.app.background and os.environ.get("ALLSET_NO_WELCOME") != "1":
        bpy.app.timers.register(_show_welcome, first_interval=0.5)


def unregister():
    global _previews
    if bpy.app.timers.is_registered(_show_welcome):
        bpy.app.timers.unregister(_show_welcome)
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
