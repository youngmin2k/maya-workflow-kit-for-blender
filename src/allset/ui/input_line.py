# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Status Line Input Line.

A mode button (Absolute transform / Relative transform / Rename / Select by name) and either three
X / Y / Z fields or one text field. Behaves like Maya 2022's Status Line
input field:

- Abs / Rel apply the current tool (Move / Rotate / Scale; any other tool = Move) to the selection on
  the axes typed in; an empty field leaves that axis alone; the fields clear afterwards.
- Rename shows the lead's name; Enter renames the selection (spaces -> "_", Maya's name rule,
  numbers for the 2nd, 3rd ... object; the single-user data follows as ``<name>Shape``).
- Select by name selects with ``*`` / ``?`` wildcards; nothing found = an error, the text stays.

The fields are Scene string properties with get / set (set = Enter), so an entry is one undo step.
Numbers are display units like the Channel Box (``ui/cb_entry.py``): ``5`` = 5 cm in the Maya Workflow Kit
layout, ``5 m`` and ``2*3`` work; rotations are degrees. X / Y / Z are Blender's axes (the Channel
Box letters). Results and errors go to the Help Line.
"""

import fnmatch
import re

import bpy
from bpy.props import BoolProperty, EnumProperty, PointerProperty, StringProperty
from mathutils import Euler, Matrix, Vector

MODES = (
    ('ABS', "Absolute Transform", "Type X / Y / Z to move, rotate or scale the selection to these values "
                                  "(the current tool; empty field = that axis stays)", 'ORIENTATION_GLOBAL', 0),
    ('REL', "Relative Transform", "Type X / Y / Z to move, rotate or scale the selection by these amounts",
     'ORIENTATION_LOCAL', 1),
    ('RENAME', "Rename", "Rename the selected objects", 'SORTALPHA', 2),
    ('SELECT', "Select by Name", "Select objects by name; * and ? are wildcards", 'VIEWZOOM', 3),
)
TOOLS = {"builtin.move": 'MOVE', "builtin.rotate": 'ROTATE', "builtin.scale": 'SCALE'}
NAME_RULE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")   # Maya's rule for a valid node name
_TRAIL = re.compile(r"^(.*?)(\d+)$")
HISTORY_PATH = "Status Line/Construction History"



def _say(text):
    from . import notices
    notices.show(text)


# --- pure-ish helpers (tests/test_step75_input_line.py) ----------------------------------------------

def clean_name(text):
    """Maya Status Line rename: spaces -> "_"; None when the name breaks Maya's rule."""
    name = text.strip().replace(" ", "_")
    return name if NAME_RULE.match(name) else None


def rename_plan(name, objects, taken):
    """New names for ``objects`` (lead first): the first gets ``name`` if free, every other one the
    lowest free ``name<N>``."""
    used = set(taken)
    out = []
    for i, _ob in enumerate(objects):
        if i == 0 and name not in used:
            new = name
        else:
            n = 1
            while f"{name}{n}" in used:
                n += 1
            new = f"{name}{n}"
        used.add(new)
        out.append(new)
    return out


def shape_name(name):
    """Maya's shape name for a transform called ``name``: box -> boxShape, box1 -> boxShape1."""
    m = _TRAIL.match(name)
    return f"{m.group(1)}Shape{m.group(2)}" if m and m.group(1) else f"{name}Shape"


def match_names(pattern, names):
    """Names matching a Maya select field entry (``*`` / ``?`` wildcards, case-sensitive)."""
    pattern = pattern.strip()
    if not pattern:
        return []
    return [n for n in names if fnmatch.fnmatchcase(n, pattern)]


# --- context ------------------------------------------------------------------------------------------

def tool_kind(context):
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, TypeError):
        tool = None
    return TOOLS.get(tool.idname if tool is not None else None, 'MOVE')


def lead(context):
    ob = context.view_layer.objects.active
    if ob is not None and ob.select_get():
        return ob
    sel = sorted(context.selected_objects, key=lambda o: o.name)
    return sel[0] if sel else None


def _values(texts, kind, scene, relative):
    """[(axis, Blender value or None)] for typed X / Y / Z; ValueError on unreadable text."""
    from . import cb_entry
    out = []
    for axis, text in enumerate(texts):
        text = (text or "").strip()
        if not text:
            out.append((axis, None))
            continue
        number = cb_entry._number(text, kind, scene)
        out.append((axis, number if (kind == "NONE") else cb_entry.from_display(number, kind, scene)))
    return out


# --- the transforms -----------------------------------------------------------------------------------

def transform(context, texts, relative):
    """Apply typed X / Y / Z (``texts``) with the current tool. Returns the number of things changed."""
    scene = context.scene
    kind = tool_kind(context)
    unit = {'MOVE': "LENGTH", 'ROTATE': "ROTATION", 'SCALE': "NONE"}[kind]
    vals = [(a, v) for a, v in _values(texts, unit, scene, relative) if v is not None]
    if not vals:
        return 0
    if context.mode == 'EDIT_MESH':
        return _transform_components(context, kind, vals, relative)
    if context.mode != 'OBJECT':
        _say("The Input Line transforms objects, or mesh components in edit mode.")
        return 0
    obs = [ob for ob in context.selected_objects if ob.visible_get()]
    for ob in obs:
        if kind == 'MOVE':
            mw = ob.matrix_world.copy()
            t = mw.translation.copy()
            for a, v in vals:
                t[a] = t[a] + v if relative else v
            mw.translation = t
            ob.matrix_world = mw
        elif kind == 'ROTATE':
            for a, v in vals:
                ob.rotation_euler[a] = ob.rotation_euler[a] + v if relative else v
        else:
            for a, v in vals:
                ob.scale[a] = ob.scale[a] * v if relative else v
    return len(obs)


def _transform_components(context, kind, vals, relative):
    import bmesh
    done = 0
    obs = context.objects_in_mode_unique_data or ()
    pts = []
    for ob in obs:
        if ob.type == 'MESH':
            bm = bmesh.from_edit_mesh(ob.data)
            pts += [ob.matrix_world @ v.co for v in bm.verts if v.select and not v.hide]
    if not pts:
        return 0
    center = sum(pts, Vector()) / len(pts)
    if kind == 'MOVE':
        offset = Vector()
        for a, v in vals:
            offset[a] = v if relative else v - center[a]
        world = Matrix.Translation(offset)
    elif kind == 'ROTATE':
        rot = Euler((0.0, 0.0, 0.0))
        for a, v in vals:
            rot[a] = v
        world = Matrix.Translation(center) @ rot.to_matrix().to_4x4() @ Matrix.Translation(-center)
    else:
        s = [1.0, 1.0, 1.0]
        for a, v in vals:
            s[a] = v
        world = Matrix.Translation(center) @ Matrix.Diagonal((*s, 1.0)) @ Matrix.Translation(-center)
    for ob in obs:
        if ob.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(ob.data)
        local = ob.matrix_world.inverted_safe() @ world @ ob.matrix_world
        for v in bm.verts:
            if v.select and not v.hide:
                v.co = local @ v.co
                done += 1
        bmesh.update_edit_mesh(ob.data)
    return done


# --- rename / select ----------------------------------------------------------------------------------

def rename(context, text):
    name = clean_name(text)
    if name is None:
        _say(f"Rename: \"{text.strip()}\" is not a valid name (letters, digits and _, not starting with a digit).")
        return []
    ld = lead(context)
    obs = [o for o in context.selected_objects if o != ld]
    obs = ([ld] if ld is not None else []) + sorted(obs, key=lambda o: o.name)
    if not obs:
        _say("Rename: nothing is selected.")
        return []
    taken = {o.name for o in bpy.data.objects if o not in obs}
    new = rename_plan(name, obs, taken)
    for ob in obs:                      # free the old names first (two selected objects may swap)
        ob.name = f"__allset_tmp_{ob.as_pointer()}"
    for ob, nm in zip(obs, new):
        ob.name = nm
        data = ob.data
        if data is not None and data.users == 1 and hasattr(data, "name"):
            data.name = shape_name(nm)
    return new


def select_by_name(context, text):
    vl = context.view_layer
    names = {}
    for ob in context.scene.objects:
        try:
            ob.select_get(view_layer=vl)
        except RuntimeError:            # not in this view layer
            continue
        if ob.visible_get() and not ob.hide_select:
            names[ob.name] = ob
    found = match_names(text, sorted(names))
    if not found:
        _say(f"Select by name: no object matches \"{text.strip()}\".")
        return []
    for ob in context.selected_objects:
        ob.select_set(False)
    for n in found:
        names[n].select_set(True)
    vl.objects.active = names[found[-1]]
    _say("Result: " + " ".join(found))
    return found


# --- the properties -----------------------------------------------------------------------------------

def _get_empty(_self):
    return ""


def _axis_setter(axis):
    def setter(self, value):
        if not value.strip():
            return
        texts = ["", "", ""]
        texts[axis] = value
        try:
            transform(bpy.context, texts, self.mode == 'REL')
        except ValueError:
            _say(f"Input Line: can't read \"{value}\".")
    return setter


def _get_text(self):
    if self.mode == 'RENAME':
        ob = lead(bpy.context)
        return ob.name if ob is not None else ""
    return self.get("pending", "")


def _set_text(self, value):
    if self.mode == 'RENAME':
        rename(bpy.context, value)
    elif self.mode == 'SELECT':
        found = select_by_name(bpy.context, value)
        self["pending"] = "" if found else value     # Maya keeps unmatched text in the field


class ALLSET_PG_input_line(bpy.types.PropertyGroup):
    mode: EnumProperty(name="Input Line", items=MODES, default='ABS',
                       description="Maya Status Line input mode")
    x: StringProperty(name="X", description="X: Enter applies the current tool (Move / Rotate / Scale)",
                      get=_get_empty, set=_axis_setter(0), options={'SKIP_SAVE'})
    y: StringProperty(name="Y", description="Y: Enter applies the current tool (Move / Rotate / Scale)",
                      get=_get_empty, set=_axis_setter(1), options={'SKIP_SAVE'})
    z: StringProperty(name="Z", description="Z: Enter applies the current tool (Move / Rotate / Scale)",
                      get=_get_empty, set=_axis_setter(2), options={'SKIP_SAVE'})
    text: StringProperty(name="Input", description="Rename: the lead's name, Enter renames the selection. "
                                                   "Select by name: * and ? are wildcards",
                         get=_get_text, set=_set_text, options={'SKIP_SAVE'})


# --- drawing ------------------------------------------------------------------------------------------

def draw_history(layout, context):
    """Maya's Construction History toggle (Maya 2022 Status Line): pressed = on."""
    layout.operator(ALLSET_OT_construction_history.bl_idname, text="", icon='RECOVER_LAST',
                    depress=context.window_manager.allset_construction_history)


def draw(layout, context):
    """Maya's input line: mode button + X / Y / Z (Abs / Rel) or one text field (Rename / Select)."""
    inp = getattr(context.scene, "allset_input", None)
    if inp is None:
        return
    row = layout.row(align=True)
    sub = row.row(align=True)
    sub.ui_units_x = 1.6
    sub.prop(inp, "mode", text="", icon_only=True)
    if inp.mode in {'ABS', 'REL'}:
        for axis in "xyz":
            cell = row.row(align=True)
            cell.ui_units_x = 2.6        # label + 40 px field
            cell.prop(inp, axis, text=axis.upper())
    else:
        cell = row.row(align=True)
        cell.ui_units_x = 8.3            # 166 px
        cell.prop(inp, "text", text="", icon='NONE')


class ALLSET_OT_construction_history(bpy.types.Operator):
    """Toggle construction history on / off (Maya Status Line): off = new primitives, extrusions and bevels keep no
    history node"""
    bl_idname = "allset.construction_history"
    bl_label = "Construction History"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        wm = context.window_manager
        wm.allset_construction_history = not wm.allset_construction_history
        from . import status_line
        status_line.redraw_top_bars()
        return {'FINISHED'}


classes = (ALLSET_PG_input_line, ALLSET_OT_construction_history)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.allset_input = PointerProperty(type=ALLSET_PG_input_line)
    bpy.types.WindowManager.allset_construction_history = BoolProperty(
        name="Construction History", default=True,
        description="Maya Construction History: off = new primitives, extrusions and bevels keep no history node "
                    "(Channel Box INPUTS / In-View Editor), like Maya")


def unregister():
    del bpy.types.WindowManager.allset_construction_history
    del bpy.types.Scene.allset_input
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
