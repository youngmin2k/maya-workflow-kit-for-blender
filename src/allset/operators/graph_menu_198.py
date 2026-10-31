# SPDX-License-Identifier: GPL-3.0-or-later
"""Graph Editor menu items (Issue #105).

- Edit > Select Unsnapped (Maya ``cmds.selectKey(unsnappedKeys=1)``,
  Graph Editor Edit menu): the keys of the shown curves whose time isn't a whole frame replace the key selection.
- Edit > Set Curve Colors... (Maya's "Curve Colors" window, rules attribute name -> colour,
  Add = the attributes of the channels selected in the editor at magenta 1 0 1, Remove): rules in the add-on pref
  ``curve_color_rules`` (JSON list of [attribute, r, g, b]); every curve of that attribute gets the colour unless the
  user coloured it (Change Curve Color) — the curves a rule coloured are recorded on their Action
  (``allset_rule_colors``) so removing a rule gives them Blender's automatic colour back.
- Keys > Add Key Tool: while the tool runs, a middle click
  in the curve area adds a key at the whole frame and the value under the mouse on the selected curves (Insert Key Tool
  keeps the curve shape instead; graph_keys.ALLSET_OT_insert_key_tool). Esc / Q W E R T end it (like the
  Retime Tool).
"""

import json

import bpy
from bpy.props import FloatVectorProperty, IntProperty, StringProperty

from .. import live_refs, preferences, results
from .graph_keys import in_dope_sheet, in_graph_editor, insert_curves, remember_selection

SNAP_TOL = 1e-4
RULE_PROP = "allset_rule_colors"
MAGENTA = (1.0, 0.0, 1.0)


# --- Select Unsnapped -----------------------------------------------------------------------------------------

def unsnapped(times, multiple=1.0, tol=SNAP_TOL):
    """Indices of ``times`` that aren't a multiple of ``multiple`` (bpy-free)."""
    out = []
    for i, t in enumerate(times):
        q = t / multiple
        if abs(q - round(q)) > tol:
            out.append(i)
    return out


def select_unsnapped(curves):
    """Replace the key selection of ``curves`` with their unsnapped keys; returns how many."""
    n = 0
    for fc in curves:
        pts = fc.keyframe_points
        hit = set(unsnapped([kp.co.x for kp in pts]))
        for i, kp in enumerate(pts):
            kp.select_control_point = i in hit
            kp.select_left_handle = kp.select_right_handle = False
        n += len(hit)
    return n


class ALLSET_OT_select_unsnapped(bpy.types.Operator):
    """Select the keys that aren't on whole frames (Maya Edit > Select Unsnapped)"""
    bl_idname = "allset.select_unsnapped"
    bl_label = "Select Unsnapped"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return in_graph_editor(context) or in_dope_sheet(context)

    def execute(self, context):
        n = select_unsnapped(getattr(context, "visible_fcurves", None) or ())
        remember_selection(context.scene)
        if context.area is not None:
            context.area.tag_redraw()
        results.result(self, f"Result: {n}")
        return {'FINISHED'}


# --- curve colour rules ---------------------------------------------------------------------------------------

def read_rules(prefs):
    """[(attribute, (r, g, b))] from the pref JSON (bad data -> no rules)."""
    try:
        raw = json.loads(prefs.curve_color_rules or "[]")
        return [(str(r[0]), (float(r[1]), float(r[2]), float(r[3]))) for r in raw if len(r) == 4]
    except (ValueError, TypeError, IndexError):
        return []


def write_rules(prefs, rules):
    prefs.curve_color_rules = json.dumps([[a, *map(float, c)] for a, c in sorted(rules, key=lambda r: r[0])])


def curve_attr(fc):
    """Maya long attribute name of a curve ("translateX"), the name rules use."""
    from ..ui import editor_chrome, graph_view
    return graph_view.maya_attr(editor_chrome.attr_label(fc))


def _key(fc):
    return f"{fc.data_path}|{fc.array_index}"


def _auto_mode(fc):
    return 'AUTO_RGB' if fc.data_path.rsplit(".", 1)[-1] in {"location", "rotation_euler", "scale"} else 'AUTO_RAINBOW'


def _close(a, b):
    return all(abs(x - y) < 1e-4 for x, y in zip(a, b))


def apply_rules(rules, actions=None):
    """Colour the curves of every Action by ``rules``; a curve the user coloured keeps its colour; curves a removed
    rule coloured go back to Blender's automatic colour. Returns the number of curves changed."""
    by_attr = dict(rules)
    changed = 0
    for act in (actions if actions is not None else bpy.data.actions):
        from .. import compat
        try:
            curves = compat.action_fcurves(act)
        except (AttributeError, TypeError):
            continue
        marks = dict(act.get(RULE_PROP, {}))
        new_marks = {}
        for fc in curves:
            k = _key(fc)
            ours = k in marks and fc.color_mode == 'CUSTOM' and _close(fc.color, marks[k])
            user = fc.color_mode == 'CUSTOM' and not ours
            want = by_attr.get(curve_attr(fc)) if by_attr else None
            if want is not None and not user:
                if not ours or not _close(fc.color, want):
                    fc.color_mode = 'CUSTOM'
                    fc.color = want
                    changed += 1
                new_marks[k] = list(want)
            elif ours:
                fc.color_mode = _auto_mode(fc)
                changed += 1
        if new_marks:
            act[RULE_PROP] = new_marks
        elif RULE_PROP in act:
            del act[RULE_PROP]
    return changed


_sig = {"rules": None, "n": -1}


def watch(context):
    """New curves get the rule colours (cheap: only when rules exist or changed, or the curve count changes)."""
    try:
        prefs = preferences.get(context)
    except KeyError:
        return
    rules = prefs.curve_color_rules
    if not rules and _sig["rules"] in (None, ""):
        return
    from .. import compat
    n = sum(len(compat.action_fcurves(a)) for a in bpy.data.actions) + len(bpy.data.actions)
    if rules == _sig["rules"] and n == _sig["n"]:
        return
    _sig.update(rules=rules, n=n)
    apply_rules(read_rules(prefs))


def _sync_from_list(context):
    wm = context.window_manager
    prefs = preferences.get(context)
    write_rules(prefs, [(r.name, tuple(r.color)) for r in wm.allset_curve_color_rules])
    apply_rules(read_rules(prefs))
    for win in wm.windows:
        for area in win.screen.areas:
            if area.type == 'GRAPH_EDITOR':
                area.tag_redraw()


def _rule_update(self, context):
    if not _loading[0]:
        _sync_from_list(context)


_loading = [False]


class ALLSET_PG_curve_color_rule(bpy.types.PropertyGroup):
    name: StringProperty(name="Attribute", update=_rule_update)
    color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0.0, max=1.0, default=MAGENTA,
                               update=_rule_update)


def _load_list(context):
    wm = context.window_manager
    _loading[0] = True
    try:
        wm.allset_curve_color_rules.clear()
        for attr, col in read_rules(preferences.get(context)):
            r = wm.allset_curve_color_rules.add()
            r.name, r.color = attr, col
    finally:
        _loading[0] = False


class ALLSET_OT_curve_color_rule_add(bpy.types.Operator):
    """Add the attributes of the selected channels to the curve colour rules (magenta)"""
    bl_idname = "allset.curve_color_rule_add"
    bl_label = "Add"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        curves = [fc for fc in (getattr(context, "visible_fcurves", None) or ()) if fc.select]
        prefs = preferences.get(context)
        rules = dict(read_rules(prefs))
        added = [curve_attr(fc) for fc in curves if curve_attr(fc) not in rules]
        if not added:
            self.report({'WARNING'}, "Select channels in the Graph Editor to add their attributes")
            return {'CANCELLED'}
        for a in added:
            rules[a] = MAGENTA
        write_rules(prefs, list(rules.items()))
        _load_list(context)
        apply_rules(read_rules(prefs))
        return {'FINISHED'}


class ALLSET_OT_curve_color_rule_remove(bpy.types.Operator):
    """Remove this curve colour rule"""
    bl_idname = "allset.curve_color_rule_remove"
    bl_label = "Remove"
    bl_options = {'INTERNAL'}

    index: IntProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        wm = context.window_manager
        if 0 <= self.index < len(wm.allset_curve_color_rules):
            wm.allset_curve_color_rules.remove(self.index)
            _sync_from_list(context)
        return {'FINISHED'}


class ALLSET_OT_curve_colors(bpy.types.Operator):
    """Edit the curve colouring rules: every curve of an attribute gets its colour (Maya Set Curve Colors)"""
    bl_idname = "allset.curve_colors"
    bl_label = "Curve Colors"

    def invoke(self, context, event):
        _load_list(context)
        return context.window_manager.invoke_popup(self, width=320)

    def execute(self, context):
        return {'FINISHED'}

    def draw(self, context):
        lay = self.layout
        lay.label(text="Curve Colors")
        col = lay.column(align=True)
        rules = context.window_manager.allset_curve_color_rules
        if not rules:
            sub = col.row()
            sub.enabled = False
            sub.label(text="(no rules)")
        for i, r in enumerate(rules):
            row = col.row(align=True)
            row.label(text=r.name)
            row.prop(r, "color", text="")
            row.operator(ALLSET_OT_curve_color_rule_remove.bl_idname, text="", icon='X').index = i
        row = lay.row(align=True)
        row.operator(ALLSET_OT_curve_color_rule_add.bl_idname, text="Add")


# --- Add Key Tool -----------------------------------------------------------------------------------------------

def add_key(fc, frame, value):
    """Maya Add Keys: a key at ``frame`` with ``value`` (an existing key there takes the value)."""
    kp = fc.keyframe_points.insert(frame, value, options={'FAST'})
    fc.update()
    return kp


class ALLSET_OT_add_key_tool(bpy.types.Operator):
    """Add Key tool: middle-click in the Graph Editor adds a key at that frame and value on the selected curves
    (Maya Add Keys Tool); Esc ends it"""
    bl_idname = "allset.add_key_tool"
    bl_label = "Add Key Tool"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'GRAPH_EDITOR'

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if region is None:
            return {'CANCELLED'}
        self._win, self._area, self._region = (context.window.as_pointer(), context.area.as_pointer(),
                                               region.as_pointer())
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Add Key Tool: middle-click adds a key on the selected curves; Esc ends")
        return {'RUNNING_MODAL'}

    def _lookup(self):
        win, area = live_refs.find_area(self._area, self._win)
        return win, area, live_refs.region(area, self._region)

    def modal(self, context, event):
        win, area, region = self._lookup()
        if region is None:
            return {'CANCELLED'}
        if event.type == 'ESC' and event.value == 'PRESS':
            return {'CANCELLED'}
        if event.type in {'Q', 'W', 'E', 'R', 'T'} and event.value == 'PRESS':
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type == 'MIDDLEMOUSE' and event.value == 'PRESS':
            x, y = event.mouse_x - region.x, event.mouse_y - region.y
            if not (0 <= x < region.width and 0 <= y < region.height):
                return {'PASS_THROUGH'}
            frame, value = region.view2d.region_to_view(x, y)
            with context.temp_override(window=win, area=area, region=region):
                curves = insert_curves(list(getattr(bpy.context, "visible_fcurves", None) or ()))
                for fc in curves:
                    for kp in fc.keyframe_points:
                        kp.select_control_point = kp.select_left_handle = kp.select_right_handle = False
                    add_key(fc, float(round(frame)), value).select_control_point = True
            if curves:
                bpy.ops.ed.undo_push(message="Add Key")
                area.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


classes = (ALLSET_OT_select_unsnapped, ALLSET_PG_curve_color_rule, ALLSET_OT_curve_color_rule_add,
           ALLSET_OT_curve_color_rule_remove, ALLSET_OT_curve_colors, ALLSET_OT_add_key_tool)


def register_props():
    bpy.types.WindowManager.allset_curve_color_rules = bpy.props.CollectionProperty(type=ALLSET_PG_curve_color_rule)


def unregister_props():
    del bpy.types.WindowManager.allset_curve_color_rules
