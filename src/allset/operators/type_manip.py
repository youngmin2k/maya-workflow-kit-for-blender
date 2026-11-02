# SPDX-License-Identifier: GPL-3.0-or-later
"""Type Manipulator: move, rotate and scale single characters of a Type node, like Maya.

Blender's text object has no per-character transforms, so the kit keeps them on the text data
(``TextCurve[XFORMS]``: character index -> offset, rotation, scale) and applies them with a Geometry Nodes
modifier on the text object. The modifier lays the same text out again with String to Curves (one instance per
character, spaces and line breaks included, so instance index = character index), fills each character, and lets
every vertex of Blender's own text geometry (fill, extrude, bevel) find the character it belongs to. Each
character then turns and scales about the middle of its box and moves by its offset. Blender's own text settings
(font, size, spacing, extrude, bevel ...) keep working: the modifier only moves vertices.

While the manipulator is on, a small handle object (``HANDLE`` ID property) stands for the picked character: the
usual Move / Rotate / Scale tools and the Channel Box act on it, and the kit writes its transform back to that
character. A click on another character of the text picks that one (``allset.type_char_pick``).
"""

import bpy
from bpy.props import IntProperty, StringProperty

TREE_PREFIX = ".Allset Type"
MOD_NAME = "Type Manipulator"
XFORMS = "allset_char_xforms"      # on the TextCurve: {"<index>": [tx, ty, tz, rx, ry, rz, sx, sy, sz]}
HANDLE = "allset_type_handle"      # on the handle object: the type object's name
CHAR = "allset_type_char"          # on the handle object: the picked character index
PIVOT = "allset_type_pivot"        # on the handle object: the picked character's rest pivot (text space)
ATTR_CHAR = "allset_char"          # point attribute of the evaluated text: character index
ATTR_PIVOT = "allset_pivot"        # point attribute of the evaluated text: the character's pivot (text space)

ALIGN_X = {'LEFT': "Left", 'CENTER': "Center", 'RIGHT': "Right", 'JUSTIFY': "Justify", 'FLUSH': "Flush"}
ALIGN_Y = {'TOP_BASELINE': "Top Baseline", 'TOP': "Top", 'CENTER': "Middle", 'BOTTOM_BASELINE': "Bottom Baseline",
           'BOTTOM': "Bottom"}
OVERFLOW = {'NONE': "Overflow", 'SCALE': "Scale To Fit", 'TRUNCATE': "Truncate"}

IDENTITY = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0)


# --- per-character values -------------------------------------------------------------------------------------

def xforms(cu):
    """{index: 9 floats} of the characters that have a transform."""
    raw = cu.get(XFORMS) if cu is not None else None
    out = {}
    if raw is None:
        return out
    for key in raw.keys():
        try:
            values = [float(v) for v in raw[key]]
        except (TypeError, ValueError):
            continue
        if len(values) == 9:
            out[int(key)] = tuple(values)
    return out


def set_xform(cu, index, values):
    """Store one character's transform (identity removes it)."""
    values = tuple(float(v) for v in values)
    raw = dict(cu.get(XFORMS, {}))
    if all(abs(a - b) < 1e-9 for a, b in zip(values, IDENTITY)):
        raw.pop(str(index), None)
    else:
        raw[str(index)] = list(values)
    cu[XFORMS] = raw
    cu.update_tag()


def clear_xforms(cu):
    if XFORMS in cu:
        del cu[XFORMS]
        cu.update_tag()


# --- the node tree -------------------------------------------------------------------------------------------

def modifier(ob):
    """The kit Type Manipulator modifier of ``ob`` or None."""
    for md in getattr(ob, "modifiers", ()):
        if is_part(md):
            return md
    return None


def is_part(md):
    """True for the kit's Type Manipulator modifier: part of the type node, not an INPUTS node of its own."""
    return md.type == 'NODES' and md.node_group is not None and md.node_group.name.startswith(TREE_PREFIX)


def _node(nodes, kind, name, x, y, **props):
    node = nodes.new(kind)
    node.name = node.label = name
    node.location = (x, y)
    for key, value in props.items():
        setattr(node, key, value)
    return node


def _store(nodes, links, name, attr, domain, data_type, geometry, value, x, y):
    st = _node(nodes, "GeometryNodeStoreNamedAttribute", name, x, y, domain=domain, data_type=data_type)
    st.inputs["Name"].default_value = attr
    links.new(geometry, st.inputs["Geometry"])
    links.new(value, st.inputs["Value"])
    return st


def _named(nodes, attr, data_type, x, y):
    node = _node(nodes, "GeometryNodeInputNamedAttribute", f"read {attr}", x, y, data_type=data_type)
    node.inputs["Name"].default_value = attr
    return node


def build_tree(name):
    """A new node tree for one type node (the per-character values are written by ``sync``)."""
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = ng.nodes, ng.links
    gi = _node(nodes, "NodeGroupInput", "Input", -1400, 0)
    go = _node(nodes, "NodeGroupOutput", "Output", 1400, 0)

    # the same text laid out again: one instance per character, filled, tagged with its index / pivot / origin
    layout = _node(nodes, "GeometryNodeStringToCurves", "Layout", -1400, 600)
    layout.inputs["Pivot Point"].default_value = "Midpoint"
    fill = _node(nodes, "GeometryNodeFillCurve", "Fill", -1200, 600)
    links.new(layout.outputs["Curve Instances"], fill.inputs["Curve"])
    index = _node(nodes, "GeometryNodeInputIndex", "Index", -1200, 400)
    position = _node(nodes, "GeometryNodeInputPosition", "Position", -1200, 300)
    st_c = _store(nodes, links, "store char", "ci", 'INSTANCE', 'INT', fill.outputs[0], index.outputs[0], -1000, 600)
    mid = _node(nodes, "ShaderNodeVectorMath", "middle", -1000, 300, operation='ADD')   # pivot is per character
    links.new(position.outputs[0], mid.inputs[0])
    links.new(layout.outputs["Pivot Point"], mid.inputs[1])
    st_p = _store(nodes, links, "store pivot", "pv", 'INSTANCE', 'FLOAT_VECTOR', st_c.outputs[0],
                  mid.outputs[0], -800, 600)
    st_o = _store(nodes, links, "store origin", "og", 'INSTANCE', 'FLOAT_VECTOR', st_p.outputs[0],
                  position.outputs[0], -600, 600)
    realize = _node(nodes, "GeometryNodeRealizeInstances", "Realize", -400, 600)
    links.new(st_o.outputs[0], realize.inputs[0])

    # Blender slants each character about its own baseline: slant the filled characters the same way
    sep = _node(nodes, "ShaderNodeSeparateXYZ", "split", -400, 400)
    links.new(position.outputs[0], sep.inputs[0])
    og = _named(nodes, "og", 'FLOAT_VECTOR', -600, 300)
    sep_og = _node(nodes, "ShaderNodeSeparateXYZ", "split origin", -400, 300)
    links.new(og.outputs["Attribute"], sep_og.inputs[0])
    rise = _node(nodes, "ShaderNodeMath", "rise", -200, 400, operation='SUBTRACT')
    links.new(sep.outputs["Y"], rise.inputs[0])
    links.new(sep_og.outputs["Y"], rise.inputs[1])
    slant = _node(nodes, "ShaderNodeMath", "Slant", 0, 400, operation='MULTIPLY')
    links.new(rise.outputs[0], slant.inputs[0])
    slant.inputs[1].default_value = 0.0
    lean = _node(nodes, "ShaderNodeCombineXYZ", "lean", 200, 400)
    links.new(slant.outputs[0], lean.inputs["X"])
    leaned = _node(nodes, "GeometryNodeSetPosition", "lean characters", 400, 600)
    links.new(realize.outputs[0], leaned.inputs["Geometry"])
    links.new(lean.outputs[0], leaned.inputs["Offset"])

    # each vertex of Blender's text geometry: the character under it (text offset taken off first)
    shift = _node(nodes, "ShaderNodeCombineXYZ", "Shift", -1200, -300)
    flat = _node(nodes, "ShaderNodeVectorMath", "flat", -1000, -200, operation='MULTIPLY')
    links.new(position.outputs[0], flat.inputs[0])
    flat.inputs[1].default_value = (1.0, 1.0, 0.0)
    unshift = _node(nodes, "ShaderNodeVectorMath", "unshift", -800, -200, operation='SUBTRACT')
    links.new(flat.outputs[0], unshift.inputs[0])
    links.new(shift.outputs[0], unshift.inputs[1])
    nearest = _node(nodes, "GeometryNodeSampleNearest", "nearest character", -600, -100, domain='FACE')
    links.new(leaned.outputs[0], nearest.inputs["Geometry"])
    links.new(unshift.outputs[0], nearest.inputs["Sample Position"])
    ci = _named(nodes, "ci", 'INT', -600, -300)
    pv = _named(nodes, "pv", 'FLOAT_VECTOR', -600, -400)
    s_char = _node(nodes, "GeometryNodeSampleIndex", "char of vertex", -400, -100, domain='FACE', data_type='INT')
    links.new(leaned.outputs[0], s_char.inputs["Geometry"])
    links.new(ci.outputs["Attribute"], s_char.inputs["Value"])
    links.new(nearest.outputs[0], s_char.inputs["Index"])
    s_piv = _node(nodes, "GeometryNodeSampleIndex", "pivot of vertex", -400, -300, domain='FACE',
                  data_type='FLOAT_VECTOR')
    links.new(leaned.outputs[0], s_piv.inputs["Geometry"])
    links.new(pv.outputs["Attribute"], s_piv.inputs["Value"])
    links.new(nearest.outputs[0], s_piv.inputs["Index"])
    pivot = _node(nodes, "ShaderNodeVectorMath", "pivot", -200, -300, operation='ADD')
    links.new(s_piv.outputs[0], pivot.inputs[0])
    links.new(shift.outputs[0], pivot.inputs[1])

    # per-character values: offset, rotation (Euler XYZ), scale - 1
    switches = []
    for k, label in enumerate(("Offsets", "Rotations", "Scales")):
        sw = _node(nodes, "GeometryNodeIndexSwitch", label, -200, -600 - 250 * k, data_type='VECTOR')
        sw.index_switch_items.clear()
        links.new(s_char.outputs[0], sw.inputs["Index"])
        switches.append(sw)
    offsets, rotations, scales = switches

    # new position = pivot + offset + R * (1 + scale) * (position - pivot)
    rel = _node(nodes, "ShaderNodeVectorMath", "from pivot", 0, -200, operation='SUBTRACT')
    links.new(position.outputs[0], rel.inputs[0])
    links.new(pivot.outputs[0], rel.inputs[1])
    one = _node(nodes, "ShaderNodeVectorMath", "1 + scale", 0, -1100, operation='ADD')
    links.new(scales.outputs[0], one.inputs[0])
    one.inputs[1].default_value = (1.0, 1.0, 1.0)
    scaled = _node(nodes, "ShaderNodeVectorMath", "scaled", 200, -200, operation='MULTIPLY')
    links.new(rel.outputs[0], scaled.inputs[0])
    links.new(one.outputs[0], scaled.inputs[1])
    back = _node(nodes, "ShaderNodeVectorMath", "back", 400, -200, operation='ADD')
    links.new(scaled.outputs[0], back.inputs[0])
    links.new(pivot.outputs[0], back.inputs[1])
    turn = _node(nodes, "ShaderNodeVectorRotate", "turned", 600, -200, rotation_type='EULER_XYZ')
    links.new(back.outputs[0], turn.inputs["Vector"])
    links.new(pivot.outputs[0], turn.inputs["Center"])
    links.new(rotations.outputs[0], turn.inputs["Rotation"])
    moved = _node(nodes, "ShaderNodeVectorMath", "moved", 800, -200, operation='ADD')
    links.new(turn.outputs[0], moved.inputs[0])
    links.new(offsets.outputs[0], moved.inputs[1])

    tag_c = _store(nodes, links, "tag char", ATTR_CHAR, 'POINT', 'INT', gi.outputs[0], s_char.outputs[0], 0, 0)
    tag_p = _store(nodes, links, "tag pivot", ATTR_PIVOT, 'POINT', 'FLOAT_VECTOR', tag_c.outputs[0],
                   pivot.outputs[0], 200, 0)
    setp = _node(nodes, "GeometryNodeSetPosition", "place characters", 1000, 0)
    links.new(tag_p.outputs[0], setp.inputs["Geometry"])
    links.new(moved.outputs[0], setp.inputs["Position"])
    links.new(setp.outputs[0], go.inputs[0])
    return ng


def _set(socket, value):
    if socket.default_value != value:
        socket.default_value = value


def _vec_set(socket, value):
    if any(abs(a - b) > 1e-9 for a, b in zip(socket.default_value, value)):
        socket.default_value = value


def sync(ob):
    """Copy the text settings and the per-character values of ``ob`` into its modifier's tree (only what
    changed, so it is safe from a depsgraph handler)."""
    md = modifier(ob)
    if md is None:
        return
    cu, ng = ob.data, md.node_group
    if ng.users > 1:                 # a duplicated type: its characters are its own
        ng = md.node_group = ng.copy()
    nodes = ng.nodes
    layout = nodes.get("Layout")
    if layout is None:
        return
    ins = layout.inputs
    _set(ins["String"], cu.body)
    if cu.font is not None and ins["Font"].default_value != cu.font:
        ins["Font"].default_value = cu.font
    _set(ins["Size"], cu.size)
    _set(ins["Character Spacing"], cu.space_character)
    _set(ins["Word Spacing"], cu.space_word)
    _set(ins["Line Spacing"], cu.space_line)
    _set(ins["Align X"], ALIGN_X.get(cu.align_x, "Left"))
    _set(ins["Align Y"], ALIGN_Y.get(cu.align_y, "Top Baseline"))
    _set(ins["Overflow"], OVERFLOW.get(cu.overflow, "Overflow"))
    box = cu.text_boxes[0] if len(cu.text_boxes) else None
    _set(ins["Text Box Width"], box.width if box is not None else 0.0)
    _set(ins["Text Box Height"], box.height if box is not None else 0.0)
    _set(nodes["Slant"].inputs[1], cu.shear)
    shift = nodes["Shift"].inputs
    _set(shift["X"], cu.offset_x + (box.x if box is not None else 0.0))
    _set(shift["Y"], cu.offset_y + (box.y if box is not None else 0.0))

    count = max(len(cu.body), 1)
    values = xforms(cu)
    for k, label in enumerate(("Offsets", "Rotations", "Scales")):
        sw = nodes[label]
        items = sw.index_switch_items
        while len(items) < count:
            items.new()
        while len(items) > count:
            items.remove(items[len(items) - 1])
        for i in range(count):
            v = values.get(i, IDENTITY)[3 * k:3 * k + 3]
            if k == 2:
                v = tuple(s - 1.0 for s in v)
            _vec_set(sw.inputs[i + 1], v)


def ensure(ob):
    """The Type Manipulator modifier of ``ob`` (made on first use), synced."""
    md = modifier(ob)
    if md is None:
        md = ob.modifiers.new(MOD_NAME, 'NODES')
        md.node_group = build_tree(f"{TREE_PREFIX} {ob.data.name}")
        md.show_expanded = False
    sync(ob)
    return md


def drop_if_unused(ob):
    """Remove the modifier (and its tree) when no character has a transform and no handle is out."""
    md = modifier(ob)
    if md is None or xforms(ob.data) or handle_of(ob) is not None:
        return
    ng = md.node_group
    ob.modifiers.remove(md)
    if ng is not None and ng.users == 0:
        bpy.data.node_groups.remove(ng)


# --- characters as seen in the viewport -----------------------------------------------------------------------

def characters(ob, depsgraph):
    """{index: (pivot in text space, (min, max) of its current vertices in text space)} from the evaluated text
    (the modifier must be on)."""
    import numpy as np
    ev = ob.evaluated_get(depsgraph)
    try:
        mesh = ev.to_mesh()
    except RuntimeError:
        return {}
    try:
        n = len(mesh.vertices)
        if n == 0 or ATTR_CHAR not in mesh.attributes or ATTR_PIVOT not in mesh.attributes:
            return {}
        co = np.empty(n * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", co)
        co = co.reshape(n, 3)
        ch = np.empty(n, dtype=np.int32)
        mesh.attributes[ATTR_CHAR].data.foreach_get("value", ch)
        pv = np.empty(n * 3, dtype=np.float32)
        mesh.attributes[ATTR_PIVOT].data.foreach_get("vector", pv)
        pv = pv.reshape(n, 3)
    finally:
        ev.to_mesh_clear()
    out = {}
    for c in np.unique(ch):
        sel = ch == c
        pts = co[sel]
        out[int(c)] = (tuple(float(x) for x in pv[sel][0]), (pts.min(0), pts.max(0)))
    return out


# --- the handle ------------------------------------------------------------------------------------------------

def handle_of(ob):
    """The handle object of the type object ``ob`` (manipulator on) or None."""
    for other in bpy.data.objects:
        if other.get(HANDLE) == ob.name and other.parent == ob:
            return other
    return None


def type_of(handle):
    """The type object a handle stands for, or None."""
    name = handle.get(HANDLE) if handle is not None else None
    ob = bpy.data.objects.get(name) if name else None
    return ob if ob is not None and ob.type == 'FONT' and handle.parent == ob else None


def handles(scene=None):
    return [ob for ob in (scene.objects if scene is not None else bpy.data.objects) if ob.get(HANDLE)]


_written = {}      # handle pointer -> the matrix_basis last written to its character / placed by the kit


def _key(handle):
    return tuple(round(v, 7) for row in handle.matrix_basis for v in row)


def place_handle(handle, ob, index, pivot):
    """Put the handle on character ``index`` (rest pivot ``pivot``, text space) with its stored transform."""
    from mathutils import Euler, Vector
    values = xforms(ob.data).get(index, IDENTITY)
    handle[CHAR] = index
    handle[PIVOT] = list(pivot)
    handle.rotation_mode = 'XYZ'
    handle.location = Vector(pivot) + Vector(values[0:3])
    handle.rotation_euler = Euler(values[3:6], 'XYZ')
    handle.scale = values[6:9]
    _written[handle.as_pointer()] = _key(handle)


def write_back(handle):
    """Store the handle's transform as its character's (when it moved since the kit last looked)."""
    ob = type_of(handle)
    if ob is None or CHAR not in handle:
        return False
    key = _key(handle)
    if _written.get(handle.as_pointer()) == key:
        return False
    _written[handle.as_pointer()] = key
    pivot = list(handle.get(PIVOT, (0.0, 0.0, 0.0)))
    loc = handle.location
    rot = handle.rotation_euler if handle.rotation_mode == 'XYZ' else handle.matrix_basis.to_euler('XYZ')
    values = (loc[0] - pivot[0], loc[1] - pivot[1], loc[2] - pivot[2], rot[0], rot[1], rot[2], *handle.scale)
    set_xform(ob.data, int(handle[CHAR]), values)
    sync(ob)
    return True


def make_handle(context, ob):
    """The handle for ``ob`` (a new one when needed), parented to it without an inverse."""
    handle = handle_of(ob)
    if handle is not None:
        return handle
    handle = bpy.data.objects.new(f"{ob.name}Manipulator", None)
    handle.empty_display_type = 'PLAIN_AXES'
    handle.empty_display_size = 0.15 * ob.data.size
    handle.hide_render = True
    handle[HANDLE] = ob.name
    for coll in ob.users_collection:
        coll.objects.link(handle)
        break
    else:
        context.scene.collection.objects.link(handle)
    handle.parent = ob
    handle.matrix_parent_inverse.identity()
    return handle


def start(context, ob):
    """Turn the Type Manipulator on for ``ob``: modifier, handle on the first character, handle selected."""
    ensure(ob)
    context.view_layer.update()
    chars = characters(ob, context.evaluated_depsgraph_get())
    if not chars:
        return None
    handle = make_handle(context, ob)
    index = min(chars)
    place_handle(handle, ob, index, chars[index][0])
    _select_only(context, handle)
    _arm()
    return handle


def stop(context, ob):
    """Turn it off: the handle goes, the text is selected again; the modifier stays while characters moved."""
    handle = handle_of(ob)
    was_selected = handle is not None and handle.select_get()
    if handle is not None:
        _written.pop(handle.as_pointer(), None)
        bpy.data.objects.remove(handle, do_unlink=True)
    drop_if_unused(ob)
    if was_selected or context.view_layer.objects.active is None:
        _select_only(context, ob)


def _select_only(context, ob):
    for other in context.view_layer.objects:
        if other is not None and other.select_get():
            other.select_set(False)
    try:
        ob.select_set(True)
    except RuntimeError:
        return
    context.view_layer.objects.active = ob


def pick(context, ob, index):
    """Make character ``index`` the handle's (False when the text has no such visible character)."""
    chars = characters(ob, context.evaluated_depsgraph_get())
    if index not in chars:
        return False
    handle = make_handle(context, ob)
    place_handle(handle, ob, index, chars[index][0])
    _select_only(context, handle)
    return True


def reset(ob, index=None):
    """Clear one character's transform (or all)."""
    if index is None:
        clear_xforms(ob.data)
    else:
        set_xform(ob.data, index, IDENTITY)
    sync(ob)
    handle = handle_of(ob)
    if handle is not None and CHAR in handle:
        place_handle(handle, ob, int(handle[CHAR]), handle.get(PIVOT, (0.0, 0.0, 0.0)))


def screen_boxes(context, ob):
    """[(index, (x0, y0, x1, y1))] of the characters' projected vertex boxes in ``context.region``."""
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    from mathutils import Vector
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return []
    mw = ob.matrix_world
    out = []
    for index, (_pivot, (lo, hi)) in characters(ob, context.evaluated_depsgraph_get()).items():
        pts = []
        for x in (lo[0], hi[0]):
            for y in (lo[1], hi[1]):
                for z in (lo[2], hi[2]):
                    p = location_3d_to_region_2d(region, rv3d, mw @ Vector((float(x), float(y), float(z))))
                    if p is not None:
                        pts.append(p)
        if pts:
            out.append((index, (min(p.x for p in pts), min(p.y for p in pts),
                                max(p.x for p in pts), max(p.y for p in pts))))
    return out


def hit(boxes, x, y):
    """The index of the smallest box holding (x, y), None when none does (pure)."""
    inside = [(abs((b[2] - b[0]) * (b[3] - b[1])), i) for i, b in boxes if b[0] <= x <= b[2] and b[1] <= y <= b[3]]
    return min(inside)[1] if inside else None


# --- keeping it live -----------------------------------------------------------------------------------------

_signatures = {}    # type object pointer -> text settings signature last synced


def _signature(ob):
    cu = ob.data
    box = cu.text_boxes[0] if len(cu.text_boxes) else None
    return (cu.body, cu.font.as_pointer() if cu.font else 0, cu.size, cu.space_character, cu.space_word,
            cu.space_line, cu.align_x, cu.align_y, cu.overflow, cu.shear, cu.offset_x, cu.offset_y,
            (box.x, box.y, box.width, box.height) if box else None, repr(sorted(xforms(cu).items())))


_armed = [False]


def _arm():
    _armed[0] = True


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    if not _armed[0]:
        return
    for ob in scene.objects:
        if ob is None:
            continue
        if ob.type == 'FONT' and modifier(ob) is not None:
            sig = _signature(ob)
            if _signatures.get(ob.as_pointer()) != sig:
                _signatures[ob.as_pointer()] = sig
                sync(ob)
        elif ob.get(HANDLE):
            write_back(ob)
            if not _selected(ob) and not _selected(type_of(ob)) and not _stopping:
                _stopping.append(ob.name)
                bpy.app.timers.register(_stop_unselected, first_interval=0.0)


def _selected(ob):
    try:
        return ob is not None and ob.select_get()
    except RuntimeError:
        return False


_stopping = []


def _stop_unselected():
    """The manipulator goes off once neither its handle nor its type is selected (another object was picked)."""
    names, _stopping[:] = list(_stopping), []
    for name in names:
        handle = bpy.data.objects.get(name)
        ob = type_of(handle)
        if ob is None or _selected(handle) or _selected(ob):
            continue
        _written.pop(handle.as_pointer(), None)
        bpy.data.objects.remove(handle, do_unlink=True)
        drop_if_unused(ob)
    return None


@bpy.app.handlers.persistent
def _on_load(*_args):
    _signatures.clear()
    _written.clear()
    _armed[0] = any(ob.type == 'FONT' and modifier(ob) is not None for ob in bpy.data.objects)


# --- operators ---------------------------------------------------------------------------------------------------

def _type_object(context):
    ob = context.active_object
    if ob is not None and ob.get(HANDLE):
        return type_of(ob)
    return ob if ob is not None and ob.type == 'FONT' else None


class ALLSET_OT_type_manipulator(bpy.types.Operator):
    """Turn the Type Manipulator on or off: click a character of the type, then move, rotate or scale it"""
    bl_idname = "allset.type_manipulator"
    bl_label = "Type Manipulator"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        if _type_object(context) is None:
            cls.poll_message_set("Select a type object")
            return False
        return context.mode == 'OBJECT'

    def execute(self, context):
        ob = _type_object(context)
        if handle_of(ob) is not None:
            stop(context, ob)
            return {'FINISHED'}
        if start(context, ob) is None:
            self.report({'WARNING'}, "The type has no characters to manipulate.")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_type_reset(bpy.types.Operator):
    """Put the picked character back (all characters with Reset All)"""
    bl_idname = "allset.type_reset"
    bl_label = "Reset Character"
    bl_options = {'UNDO'}

    all: bpy.props.BoolProperty(name="All Characters", default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        ob = _type_object(context)
        return ob is not None and modifier(ob) is not None

    def execute(self, context):
        ob = _type_object(context)
        handle = handle_of(ob)
        if self.all or handle is None or CHAR not in handle:
            reset(ob)
        else:
            reset(ob, int(handle[CHAR]))
        if handle is None:
            drop_if_unused(ob)
        return {'FINISHED'}


class ALLSET_OT_type_char_pick(bpy.types.Operator):
    """Pick a character of a type whose Type Manipulator is on"""
    bl_idname = "allset.type_char_pick"
    bl_label = "Pick Character"
    bl_options = {'INTERNAL', 'UNDO'}

    index: IntProperty(default=-1, options={'SKIP_SAVE'})
    type_object: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        ob = bpy.data.objects.get(self.type_object)
        if ob is None or self.index < 0 or not pick(context, ob, self.index):
            return {'CANCELLED'}
        return {'FINISHED'}

    def invoke(self, context, event):
        if context.mode != 'OBJECT' or context.region is None or context.region_data is None:
            return {'PASS_THROUGH'}
        x, y = event.mouse_region_x, event.mouse_region_y
        for handle in handles(context.scene):
            ob = type_of(handle)
            if ob is None or not ob.visible_get():
                continue
            index = hit(screen_boxes(context, ob), x, y)
            if index is not None:
                self.type_object, self.index = ob.name, index
                return self.execute(context)
        return {'PASS_THROUGH'}


# --- drawing: character boxes while the manipulator is on ------------------------------------------------------

_draw_handle = [None]
PICKED = (1.0, 0.85, 0.3, 1.0)      # the picked character's box
OTHER = (0.55, 0.55, 0.55, 0.8)     # the other characters' boxes


def _draw():
    context = bpy.context
    scene = context.scene
    if scene is None or not _armed[0]:
        return
    hs = handles(scene)
    if not hs:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    region = context.region
    depsgraph = context.evaluated_depsgraph_get()
    for handle in hs:
        ob = type_of(handle)
        if ob is None or not ob.visible_get():
            continue
        picked = int(handle.get(CHAR, -1))
        mw = ob.matrix_world
        for index, (_pivot, (lo, hi)) in characters(ob, depsgraph).items():
            corners = [mw @ _v(lo[0], lo[1], lo[2]), mw @ _v(hi[0], lo[1], lo[2]),
                       mw @ _v(hi[0], hi[1], lo[2]), mw @ _v(lo[0], hi[1], lo[2])]
            lines = []
            for a, b in zip(corners, corners[1:] + corners[:1]):
                lines += [a, b]
            batch = batch_for_shader(shader, 'LINES', {"pos": lines})
            shader.uniform_float("viewportSize", (region.width, region.height))
            shader.uniform_float("lineWidth", 2.0 if index == picked else 1.0)
            shader.uniform_float("color", PICKED if index == picked else OTHER)
            batch.draw(shader)


def _v(x, y, z):
    from mathutils import Vector
    return Vector((float(x), float(y), float(z)))


classes = (ALLSET_OT_type_manipulator, ALLSET_OT_type_reset, ALLSET_OT_type_char_pick)


def register_handlers():
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    bpy.app.handlers.load_post.append(_on_load)
    _draw_handle[0] = bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW')
    _on_load()


def unregister_handlers():
    if _draw_handle[0] is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle[0], 'WINDOW')
        _draw_handle[0] = None
    for lst, fn in ((bpy.app.handlers.depsgraph_update_post, _on_depsgraph), (bpy.app.handlers.load_post, _on_load)):
        if fn in lst:
            lst.remove(fn)
    _signatures.clear()
    _written.clear()
