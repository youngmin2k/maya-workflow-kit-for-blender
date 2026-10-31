# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's Connection Editor window (Issue #119).

Maya 2022: Reload Left / Reload Right, the mode buttons
Outputs / from -> to / Inputs, two attribute lists (the node, then its attributes; compounds such as translate open
to translateX / Y / Z), the node names under the lists with < > to swap them, and Clear All / Remove / Break / Make /
Close. With Auto-connect on (factory) a click on a left attribute then on a right one connects them: the right one
follows the left (``connectAttr``); a click on a connected right attribute breaks it, the value stays.

Blender has no dependency graph connections between properties: a connection is a driver on the right property with
one variable ``cn`` reading the left property (the Set Driven Key driver uses ``sdk`` the same way). Maya copies the number
across attribute types through unit conversion (translateX 3 cm -> rotateX 3 degrees), so the driver expression scales
by the same Maya-number factors (lengths / ``maya_unit()``, angles in degrees). Only attributes with a Blender
counterpart are listed (transform channels, visibility, custom attributes): Maya's caching / nodeState / ... have none.
"""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import marked_window

KIND = "CONNECTION_EDITOR"
EDITOR = "Connection Editor"
VAR = "cn"
SIDES = (("LEFT", "Left", ""), ("RIGHT", "Right", ""))
MODES = (("OUTPUTS", "Outputs", "Both lists show outputs: connect left to right"),
         ("FROM_TO", "from -> to", "Connect a left output to a right input"),
         ("INPUTS", "Inputs", "Both lists show inputs: connect right to left"))

# Maya long name -> (Blender path, index, kind); compounds -> their children (Maya's readable list, ui/channel_box MAIN)
SIMPLE = {}
COMPOUNDS = {}
for _maya, _path, _kind in (("translate", "location", "LOC"), ("rotate", "rotation_euler", "ROT"),
                            ("scale", "scale", "SCALE")):
    COMPOUNDS[_maya] = [f"{_maya}{axis}" for axis in "XYZ"]
    for _i, _axis in enumerate("XYZ"):
        SIMPLE[f"{_maya}{_axis}"] = (_path, _i, _kind)
SIMPLE["visibility"] = ("hide_viewport", -1, "VIS")
ORDER = ("visibility", "translate", "rotate", "scale")


# --- attributes ----------------------------------------------------------------------------------------------------

def custom_attrs(ob):
    """Custom (user) attributes: numeric ID properties that aren't the kit's bookkeeping."""
    out = []
    for key in ob.keys():
        if key.startswith(("_", "allset", "cycles")):
            continue
        if isinstance(ob[key], (int, float)) and not isinstance(ob[key], bool):
            out.append(key)
    return out


def attributes(ob):
    """[(name, depth, is_compound)] in Maya's list order: visibility, translate ▸ X Y Z, rotate ▸, scale ▸, custom."""
    rows = []
    for name in ORDER:
        if name in COMPOUNDS:
            rows.append((name, 0, True))
            rows.extend((child, 1, False) for child in COMPOUNDS[name])
        else:
            rows.append((name, 0, False))
    rows.extend((key, 0, False) for key in custom_attrs(ob))
    return rows


def resolve(ob, attr):
    """(data path, index, kind) of a simple attribute of ``ob`` (custom ones are ``["key"]``)."""
    if attr in SIMPLE:
        return SIMPLE[attr]
    if ob is not None and attr in ob.keys():
        return (f'["{attr}"]', -1, "CUSTOM")
    return None


def leaves(attr):
    return COMPOUNDS.get(attr, [attr])


def maya_factor(kind, unit):
    """Blender value x factor = the Maya number (lengths in Maya units, angles in degrees)."""
    if kind == "LOC":
        return 1.0 / unit
    if kind == "ROT":
        return 180.0 / math.pi
    return 1.0


def expression(src_kind, dst_kind, unit):
    """The driver expression: Maya's unit conversion between the two attribute kinds."""
    k = maya_factor(src_kind, unit) / maya_factor(dst_kind, unit)
    return VAR if abs(k - 1.0) < 1e-12 else f"{VAR} * {k!r}"


def _unit(scene):
    from ..operators import units
    return units.maya_unit(scene)


def _fcurve(ob, path, index):
    ad = ob.animation_data
    if ad is None:
        return None
    for fc in ad.drivers:
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            return fc
    return None


def source_of(ob, attr):
    """(source object, source attribute) feeding ``ob.attr`` through a kit connection, else None."""
    res = resolve(ob, attr)
    if res is None:
        return None
    fc = _fcurve(ob, res[0], res[1])
    if fc is None:
        return None
    var = next((v for v in fc.driver.variables if v.name == VAR), None)
    if var is None or not var.targets or var.targets[0].id is None:
        return None
    src, path = var.targets[0].id, var.targets[0].data_path
    for name, (p, i, _k) in SIMPLE.items():
        if path == (f"{p}[{i}]" if i >= 0 else p):
            return src, name
    if path.startswith('["') and path.endswith('"]'):
        return src, path[2:-2]
    return None


def connected(src, src_attr, dst, dst_attr):
    """True when every leaf of ``dst_attr`` is fed by the matching leaf of ``src.src_attr``."""
    pairs = list(zip(leaves(src_attr), leaves(dst_attr)))
    return bool(pairs) and all(source_of(dst, d) == (src, s) for s, d in pairs)


def connect(scene, src, src_attr, dst, dst_attr):
    """Maya connectAttr src.attr -> dst.attr (compounds connect child by child). Returns the connected leaf count;
    raises ValueError when the attributes don't match (Maya: compound to simple / different sizes)."""
    sl, dl = leaves(src_attr), leaves(dst_attr)
    if len(sl) != len(dl):
        raise ValueError(f"The attributes {src.name}.{src_attr} and {dst.name}.{dst_attr} are not compatible")
    if src == dst and src_attr == dst_attr:
        raise ValueError("Cannot connect an attribute to itself")
    unit = _unit(scene)
    n = 0
    for s, d in zip(sl, dl):
        sres, dres = resolve(src, s), resolve(dst, d)
        if sres is None or dres is None:
            raise ValueError(f"No such attribute: {s if sres is None else d}")
        path, index, kind = dres
        old = _fcurve(dst, path, index)
        if old is not None:          # a driver already there (another connection, an SDK curve): replace it
            dst.driver_remove(path, index) if index >= 0 else dst.driver_remove(path)
        # a new driver F-curve maps its value through as is (4.5: a Generator modifier, 5.x: keys (0, 0) (1, 1))
        fc = dst.driver_add(path, index) if index >= 0 else dst.driver_add(path)
        drv = fc.driver
        drv.type = 'SCRIPTED'
        var = drv.variables.new()
        var.name = VAR
        var.type = 'SINGLE_PROP'
        var.targets[0].id_type = 'OBJECT'
        var.targets[0].id = src
        var.targets[0].data_path = f"{sres[0]}[{sres[1]}]" if sres[1] >= 0 else sres[0]
        drv.expression = expression(sres[2], kind, unit)
        n += 1
    # a Python ID-property write tags nothing: a custom attribute made after the last evaluation
    # isn't on the evaluated source yet, and the driver reads it as invalid until the source is tagged
    src.update_tag()
    dst.update_tag()
    return n


def disconnect(dst, dst_attr):
    """Maya disconnectAttr: the driver goes, the attribute keeps its last value (CN3). Returns the leaf count."""
    n = 0
    for d in leaves(dst_attr):
        res = resolve(dst, d)
        if res is None or source_of(dst, d) is None:
            continue
        path, index, _kind = res
        value = getattr(dst, path) if not path.startswith("[") else dst[path[2:-2]]
        keep = value[index] if index >= 0 else value
        if index >= 0:
            dst.driver_remove(path, index)
            getattr(dst, path)[index] = keep
        elif path.startswith("["):
            dst.driver_remove(path)
            dst[path[2:-2]] = keep
        else:
            dst.driver_remove(path)
            setattr(dst, path, keep)
        n += 1
    return n


# --- window state --------------------------------------------------------------------------------------------------

def _wm(context):
    return context.window_manager


def node(context, side):
    name = getattr(_wm(context), f"allset_cn_{side.lower()}")
    return bpy.data.objects.get(name) if name else None


def _open_key(side, attr):
    return f"{side}:{attr}"


def is_open(context, side, attr):
    return _open_key(side, attr) in _wm(context).allset_cn_open.split(",")


def direction(context):
    """(source side, target side) for the current mode (Inputs connects right to left)."""
    return ("RIGHT", "LEFT") if _wm(context).allset_cn_mode == "INPUTS" else ("LEFT", "RIGHT")


def _redraw(context):
    marked_window.redraw(context, KIND)


class ALLSET_OT_connection_editor(bpy.types.Operator):
    """Open the Connection Editor: connect an attribute of the left node to one of the right node (Maya Windows >
    General Editors > Connection Editor; Blender: a driver)"""
    bl_idname = "allset.connection_editor"
    bl_label = "Connection Editor"

    def execute(self, context):
        if context.window is None:
            return {'CANCELLED'}
        wm = _wm(context)
        sel = [o for o in context.selected_objects]
        # Maya loads the selection: the first on the left, the last (if another) on the right
        if sel and not wm.allset_cn_left:
            wm.allset_cn_left = sel[0].name
        if len(sel) > 1 and not wm.allset_cn_right:
            wm.allset_cn_right = sel[-1].name
        if marked_window.open_window(context, KIND) is None:
            from . import window_places
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open the Connection Editor window")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_cn_reload(bpy.types.Operator):
    """Load the selected object into this side (Maya Reload Left / Reload Right)"""
    bl_idname = "allset.cn_reload"
    bl_label = "Reload"
    bl_options = {'INTERNAL'}

    side: EnumProperty(items=SIDES, options={'SKIP_SAVE'})

    def execute(self, context):
        ob = context.active_object or next(iter(context.selected_objects), None)
        if ob is None:
            self.report({'WARNING'}, "Select an object to load")
            return {'CANCELLED'}
        setattr(_wm(context), f"allset_cn_{self.side.lower()}", ob.name)
        setattr(_wm(context), f"allset_cn_{self.side.lower()}_attr", "")
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_cn_pick(bpy.types.Operator):
    """Pick this attribute; with Auto-connect a pick on the other side connects (or, if connected, breaks) the pair"""
    bl_idname = "allset.cn_pick"
    bl_label = "Pick Attribute"
    bl_options = {'INTERNAL', 'UNDO'}

    side: EnumProperty(items=SIDES, options={'SKIP_SAVE'})
    attr: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        wm = _wm(context)
        setattr(wm, f"allset_cn_{self.side.lower()}_attr", self.attr)
        src_side, dst_side = direction(context)
        if wm.allset_cn_auto and self.side == dst_side:
            src_attr = getattr(wm, f"allset_cn_{src_side.lower()}_attr")
            src, dst = node(context, src_side), node(context, dst_side)
            if src is not None and dst is not None and src_attr:
                try:
                    if connected(src, src_attr, dst, self.attr):
                        disconnect(dst, self.attr)
                    else:
                        connect(context.scene, src, src_attr, dst, self.attr)
                except ValueError as ex:
                    self.report({'WARNING'}, str(ex))
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_cn_toggle(bpy.types.Operator):
    """Open / close this compound attribute"""
    bl_idname = "allset.cn_toggle"
    bl_label = "Expand"
    bl_options = {'INTERNAL'}

    side: EnumProperty(items=SIDES, options={'SKIP_SAVE'})
    attr: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        wm = _wm(context)
        keys = [k for k in wm.allset_cn_open.split(",") if k]
        key = _open_key(self.side, self.attr)
        keys = [k for k in keys if k != key] if key in keys else keys + [key]
        wm.allset_cn_open = ",".join(keys)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_cn_command(bpy.types.Operator):
    """Connection Editor buttons: Make, Break, swap sides, Clear All, Remove"""
    bl_idname = "allset.cn_command"
    bl_label = "Connection Editor"
    bl_options = {'INTERNAL', 'UNDO'}

    action: EnumProperty(items=(("MAKE", "Make", "Connect the picked attributes"),
                                ("BREAK", "Break", "Disconnect the picked right attribute"),
                                ("SWAP", "Swap", "Swap the left and right nodes"),
                                ("CLEAR", "Clear All", "Empty both lists"),
                                ("REMOVE", "Remove", "Empty the right list")), options={'SKIP_SAVE'})

    def execute(self, context):
        wm = _wm(context)
        src_side, dst_side = direction(context)
        src, dst = node(context, src_side), node(context, dst_side)
        src_attr = getattr(wm, f"allset_cn_{src_side.lower()}_attr")
        dst_attr = getattr(wm, f"allset_cn_{dst_side.lower()}_attr")
        if self.action == "MAKE":
            if src is None or dst is None or not src_attr or not dst_attr:
                self.report({'WARNING'}, "Pick an attribute on each side")
                return {'CANCELLED'}
            try:
                connect(context.scene, src, src_attr, dst, dst_attr)
            except ValueError as ex:
                self.report({'WARNING'}, str(ex))
                return {'CANCELLED'}
        elif self.action == "BREAK":
            if dst is None or not dst_attr or not disconnect(dst, dst_attr):
                self.report({'WARNING'}, "No connection to break")
                return {'CANCELLED'}
        elif self.action == "SWAP":
            wm.allset_cn_left, wm.allset_cn_right = wm.allset_cn_right, wm.allset_cn_left
            wm.allset_cn_left_attr, wm.allset_cn_right_attr = wm.allset_cn_right_attr, wm.allset_cn_left_attr
        elif self.action == "CLEAR":
            wm.allset_cn_left = wm.allset_cn_right = wm.allset_cn_left_attr = wm.allset_cn_right_attr = ""
        elif self.action == "REMOVE":
            wm.allset_cn_right = wm.allset_cn_right_attr = ""
        _redraw(context)
        return {'FINISHED'}


# --- drawing -------------------------------------------------------------------------------------------------------

def _nice(name):
    """Maya Channel Names > Nice: translateX -> Translate X."""
    out = name[0].upper()
    for ch in name[1:]:
        out += (" " + ch) if ch.isupper() else ch
    return out


def draw_list(layout, context, side):
    wm = _wm(context)
    ob = node(context, side)
    col = layout.column(align=True)
    if ob is None:
        col.label(text="(empty)")
        return
    col.label(text=ob.name, icon='OBJECT_DATA')
    picked = getattr(wm, f"allset_cn_{side.lower()}_attr")
    _src_side, dst_side = direction(context)
    for name, depth, compound in attributes(ob):
        if depth and not any(is_open(context, side, c) for c, kids in COMPOUNDS.items() if name in kids):
            continue
        row = col.row(align=True)
        if depth:
            row.separator(factor=2.0)
        if compound:
            op = row.operator(ALLSET_OT_cn_toggle.bl_idname, text="", emboss=False,
                              icon='DISCLOSURE_TRI_DOWN' if is_open(context, side, name) else 'DISCLOSURE_TRI_RIGHT')
            op.side, op.attr = side, name
        # a fed attribute (every leaf has a kit connection) shows the driver icon, like Maya's connected rows
        linked = side == dst_side and all(source_of(ob, leaf) is not None for leaf in leaves(name))
        label = _nice(name) if wm.allset_cn_names == "NICE" else name
        cell = row.row(align=True)
        cell.alignment = 'LEFT'          # Maya's attribute names start at the left
        op = cell.operator(ALLSET_OT_cn_pick.bl_idname, text=label, depress=name == picked,
                           icon='DRIVER' if linked else 'NONE', emboss=name == picked)
        op.side, op.attr = side, name


class ALLSET_PT_connection_editor(bpy.types.Panel):
    """Maya's Connection Editor (a marked Properties Tool tab in its own window)"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"
    bl_label = "Connection Editor"
    bl_options = {'HIDE_HEADER'}
    bl_order = -300

    @classmethod
    def poll(cls, context):
        return marked_window.context_kind(context) == KIND

    def draw(self, context):
        wm = _wm(context)
        layout = self.layout
        marked_window.draw_menu_bar(layout, context, EDITOR)
        row = layout.row(align=True)
        for side, text in (("LEFT", "Reload Left"), ("RIGHT", "Reload Right")):
            row.operator(ALLSET_OT_cn_reload.bl_idname, text=text).side = side
        layout.row(align=True).prop(wm, "allset_cn_mode", expand=True)
        split = layout.split(factor=0.5)
        draw_list(split.box(), context, "LEFT")
        draw_list(split.box(), context, "RIGHT")
        names = layout.row(align=True)
        names.label(text=wm.allset_cn_left or " ")
        sw = names.row(align=True)
        sw.operator(ALLSET_OT_cn_command.bl_idname, text="", icon='TRIA_LEFT').action = "SWAP"
        sw.operator(ALLSET_OT_cn_command.bl_idname, text="", icon='TRIA_RIGHT').action = "SWAP"
        names.label(text=wm.allset_cn_right or " ")
        bottom = layout.row(align=True)
        for action, text in (("CLEAR", "Clear All"), ("REMOVE", "Remove"), ("BREAK", "Break"), ("MAKE", "Make")):
            bottom.operator(ALLSET_OT_cn_command.bl_idname, text=text).action = action
        bottom.operator("allset.marked_window_close", text="Close")


classes = (ALLSET_OT_connection_editor, ALLSET_OT_cn_reload, ALLSET_OT_cn_pick, ALLSET_OT_cn_toggle,
           ALLSET_OT_cn_command, ALLSET_PT_connection_editor)

_WM_PROPS = ("allset_cn_left", "allset_cn_right", "allset_cn_left_attr", "allset_cn_right_attr", "allset_cn_open",
             "allset_cn_mode", "allset_cn_auto", "allset_cn_names")


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    wm = bpy.types.WindowManager
    wm.allset_cn_left = StringProperty(name="Left Node")
    wm.allset_cn_right = StringProperty(name="Right Node")
    wm.allset_cn_left_attr = StringProperty(name="Left Attribute")
    wm.allset_cn_right_attr = StringProperty(name="Right Attribute")
    wm.allset_cn_open = StringProperty(name="Open Compounds")
    wm.allset_cn_mode = EnumProperty(name="Mode", items=MODES, default="FROM_TO")
    wm.allset_cn_auto = BoolProperty(name="Auto-connect", default=True,
                                     description="A pick on the right connects / breaks at once (on by default, like Maya)")
    wm.allset_cn_names = EnumProperty(name="Channel Names", default="LONG",
                                      items=(("NICE", "Nice", ""), ("LONG", "Long", ""), ("SHORT", "Short", "")))


def unregister():
    for name in _WM_PROPS:
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
