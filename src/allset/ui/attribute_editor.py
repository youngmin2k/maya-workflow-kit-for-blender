# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Attribute Editor in the 3D View sidebar, sharing the Channel Box dock.

Maya's Attribute Editor.
- Dock mode (``WindowManager.allset_dock``): the sidebar tabs "Channel Box / Layer
  Editor", "Attribute Editor", "Modeling Toolkit" = the tabs of Maya's right dock
 ; Ctrl+A toggles
  (``ShowAttributeEditorOrChannelBox``).
- Node tabs: transform = object, shape = object
  data, one tab per modifier (construction history inputs) and per material.
- Sections and their rows: ``ae_layout`` (Maya template sections, collapse flags
  from Maya's Attribute Editor templates), drawn as ``layout.panel`` sections.
- Joints: in pose mode the node is the lead pose bone (``channel_box.lead``): a
  ``joint`` tab (ae_layout.JOINT) plus one tab per constraint node, like Maya's
  ``pCube1_parentConstraint1``.
- Maya's Attribute Editor:
  the kit's last extrusion is a ``polyExtrudeFace`` history tab (``H``), modifiers are tabs with Maya node names
  (``MODIFIER_NODES``), and Maya's AE chrome: menu bar List / Selected / Focus / Attributes / Display / Show / Help,
  Focus / Presets / Show / Hide beside the node name, Notes, and Select / Load Attributes / Copy Tab at the bottom.
"""

import math
import re

import bpy
from bpy.props import EnumProperty, StringProperty

from .. import results
from .. import compat, live_refs
from ..operators import display
from . import ae_layout
from . import cb_entry, channel_box

DOCK_ITEMS = (('CHANNEL_BOX', "Channel Box / Layer Editor", "Maya Channel Box and Layer Editor"),
              ('ATTRIBUTE_EDITOR', "Attribute Editor", "Maya Attribute Editor"),
              ('MODELING_TOOLKIT', "Modeling Toolkit", "Maya Modeling Toolkit (ui/modeling_toolkit.py)"))


def dock_mode(context):
    return getattr(context.window_manager, "allset_dock", 'CHANNEL_BOX')


# --- tabs ---------------------------------------------------------------------------------

def principled(material):
    if not compat.material_uses_nodes(material):
        return None
    return next((n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)


def material_type(material):
    """Maya node type of a material: the type a kit-made material recorded (lambert, blinn,
    phong, standardSurface, surfaceShader; operators/material.py), else standardSurface for a
    Principled material, else "material"."""
    if material is None:
        return "material"
    from ..operators.material import TYPE_PROP
    recorded = material.get(TYPE_PROP)
    if isinstance(recorded, str) and recorded in ae_layout.BY_KIND and principled(material):
        return recorded
    return "standardSurface" if principled(material) else "material"


def node_type(ob):
    if ob.type == 'LIGHT':
        return ae_layout.light_type(ob.data)
    return ae_layout.NODE_TYPE.get(ob.type, ob.type.lower())


# Blender modifier -> the Maya history node that does the same (Maya node type names; where Maya has
# none of its own: the closest poly / deformer node).
MODIFIER_NODES = {
    'SUBSURF': "polySmoothFace", 'MULTIRES': "polySmoothFace", 'BEVEL': "polyBevel3", 'MIRROR': "polyMirror",
    'TRIANGULATE': "polyTriangulate", 'WELD': "polyMergeVert", 'DECIMATE': "polyReduce", 'REMESH': "polyRemesh",
    'SOLIDIFY': "polyExtrudeFace", 'BOOLEAN': "polyCBoolOp", 'SMOOTH': "polyAverageVertex",
    'LAPLACIANSMOOTH': "polyAverageVertex", 'CORRECTIVE_SMOOTH': "deltaMush", 'ARMATURE': "skinCluster",
    'LATTICE': "ffd", 'SHRINKWRAP': "shrinkWrap", 'WIREFRAME': "polyWireframe", 'ARRAY': "polyDuplicate",
    'CLOTH': "nCloth", 'COLLISION': "nRigid", 'PARTICLE_SYSTEM': "nParticle", 'SOFT_BODY': "nCloth",
    'SIMPLE_DEFORM': "nonLinear", 'CAST': "nonLinear", 'WAVE': "nonLinear", 'DISPLACE': "textureDeformer",
    'SCREW': "polyRevolve", 'EDGE_SPLIT': "polySoftEdge",
    'WEIGHTED_NORMAL': "polyNormalPerVertex", 'NODES': "geometryNodes",
    'HOOK': "cluster", 'SURFACE_DEFORM': "wrap", 'CURVE': "curveWarp",    # operators/deformers.BASES
}


def modifier_node(ob, md):
    """(Maya node name, Maya node type) of a modifier: a modifier with Blender's automatic name gets Maya's
    (``<type><n>``, numbered per type like Maya: ``polyBevel1``); a named one (kit-made ``polySmoothFace``, the
    user's own) keeps its name."""
    from ..operators import deformers
    kit = deformers.node_type(md)     # a kit Maya deformer (cluster1 = HOOK, wrap1 = SURFACE_DEFORM ...)
    if kit is not None:
        return md.name, kit
    mtype = MODIFIER_NODES.get(md.type, md.type.lower())
    base = re.sub(r"\d+$", "", mtype)         # Maya names polyBevel3 nodes polyBevel1, polyBevel2, ...
    if not default_name(md):
        return md.name, mtype                  # a name the user / the kit gave it
    same = [m for m in ob.modifiers if MODIFIER_NODES.get(m.type, m.type.lower()) == mtype
            and not display.is_preview(m) and default_name(m)]
    return f"{base}{same.index(md) + 1}", mtype


def default_name(md):
    """True for Blender's automatic modifier names ("Bevel", "Subdivision.001", "GeometryNodes")."""
    base = re.sub(r"\.\d+$", "", md.name).replace(" ", "").lower()
    ui = md.bl_rna.properties["type"].enum_items[md.type].name.replace(" ", "").lower()
    return bool(base) and ui.startswith(base)


def history_record(ob):
    """The kit's last extrusion of ``ob`` (Maya polyExtrudeFace node), or None (edit mode only)."""
    from . import in_view
    try:
        return in_view.cb_record(bpy.context, ob)
    except (AttributeError, ReferenceError):
        return None


def nice_type(mtype):
    """"polyExtrudeFace" -> "Poly Extrude Face" (Maya's history section title is "<Nice Type> History")."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", mtype[:1].upper() + mtype[1:])


def hidden_types(context=None):
    wm = (context or bpy.context).window_manager
    return {t for t in getattr(wm, "allset_ae_hidden", "").split(",") if t}


def _constraint_tabs(node):
    return [(f"C:{con.name}", channel_box.constraint_node_name(node, con),
             channel_box.maya_constraint_type(con, con.type.lower()))
            for con in channel_box.constraints(node)]


def tabs(ob):
    """[(key, label, Maya node type)] in Maya's order: transform, shape, history, materials,
    constraints; a joint (pose bone): joint, constraints."""
    if channel_box.is_bone(ob):
        return [("J", ob.name, "joint")] + _constraint_tabs(ob)
    out = [("T", ob.name, "transform")]
    if ob.data is not None:
        out.append(("S", ob.data.name, node_type(ob)))
    rec = history_record(ob)
    if rec is not None:
        from ..operators import model_history
        nodes = model_history.records(ob)
        if nodes:
            for index, node in enumerate(reversed(nodes)):
                out.append(('H' if index == 0 else 'H:'+node.history_id, node.name, node.spec.node_type))
        else:
            out.append(('H', rec.name, rec.spec.node_type))
    from ..operators import skin_tools_199
    for md in ob.modifiers:
        if display.is_preview(md):   # shape display attribute, drawn in "Smooth Mesh"
            continue
        if skin_tools_199.is_part(md):   # the skin's weight-sum helper belongs to the skinCluster
            continue
        from ..operators import skin_method
        if skin_method.is_part(md):      # Weight Blended's DQ half belongs to the skinCluster too
            continue
        from ..operators import type_manip
        if type_manip.is_part(md):       # the type node's own per-character transforms
            continue
        name, mtype = modifier_node(ob, md)
        out.append((f"M:{md.name}", name, mtype))
    from ..operators import prim_history
    _owner, node = prim_history.node_of(ob)
    if node is not None:             # the primitive's creation node, the oldest history
        out.append(("CH", node["name"], node["type"]))
    from ..operators import material as material_ops
    for i, slot in enumerate(ob.material_slots):
        if slot.material is not None:
            # Maya: the shape's shading group, then its surface shader (pCubeShape1 | polyCube1 |
            # initialShadingGroup | lambert1)
            out.append((f"SG:{i}", material_ops.shading_group_name(slot.material), "shadingEngine"))
            out.append((f"MAT:{i}", slot.material.name, material_type(slot.material)))
    out += _constraint_tabs(ob)
    hide = hidden_types()             # AE Hide button: nodes of these types get no tab (the node itself stays)
    return [t for t in out if t[0] in ("T", "S") or t[2] not in hide]


def _kind(key):
    return key.split(":", 1)[0]


def current_tab(context, ob):
    """The selected tab key: the stored one, else the first of the stored kind, else
    the shape (Maya's preferred node), else the transform."""
    wm = context.window_manager
    keys = [t[0] for t in tabs(ob)]
    if wm.allset_ae_tab in keys:
        return wm.allset_ae_tab
    for k in keys:
        if _kind(k) == wm.allset_ae_kind:
            return k
    if "J" in keys:
        return "J"
    return "S" if "S" in keys else "T"


def tab_target(ob, key):
    """The datablock or modifier a tab shows."""
    kind = _kind(key)
    if kind in ("T", "J"):
        return ob
    if kind == "C":
        return ob.constraints.get(key[2:])
    if kind == "S":
        return ob.data
    if kind == "M":
        return ob.modifiers.get(key[2:])
    if kind in ("MAT", "SG"):
        i = int(key.split(":", 1)[1])
        return ob.material_slots[i].material if i < len(ob.material_slots) else None
    if kind == "H":
        from ..operators import model_history
        if ':' in key:
            return model_history.find(ob, key.split(':', 1)[1])
        nodes = model_history.records(ob)
        return nodes[-1] if nodes else history_record(ob)
    if kind == "CH":
        from ..operators import prim_history
        return prim_history.node_of(ob)[0]
    return None


def sections_for(ob, key):
    """(sections, layout id) for a tab; empty for history tabs (drawn generically)."""
    kind = _kind(key)
    if kind == "T":
        return ae_layout.BY_KIND["transform"][0], "transform"
    if kind == "J":
        return ae_layout.BY_KIND["joint"][0], "joint"
    if kind == "S":
        sub = ob.data.type if ob.type == 'LIGHT' else ob.type
        return ae_layout.BY_KIND.get(sub, ([], None))[0], sub.lower()
    if kind == "MAT":
        mat = tab_target(ob, key)
        name = material_type(mat)
        return ae_layout.BY_KIND[name][0], name
    return [], None


# --- drawing --------------------------------------------------------------------------------

def resolve(owner, path):
    """(object, attribute) for a dotted path such as ``overlay.show_face_normals``."""
    *head, attr = path.split(".")
    for part in head:
        owner = getattr(owner, part, None)
        if owner is None:
            return None, attr
    return owner, attr


def _owner(context, ob, target, name):
    if name == "ob":
        return ob
    if name == "data":
        return target
    if name == "view":
        space = context.space_data
        return space if space is not None and space.type == 'VIEW_3D' else None
    if channel_box.is_bone(ob):
        return {"bone": ob.bone, "arm": ob.id_data.data, "armob": ob.id_data}.get(name)
    return None


def _length(context, value):
    us = context.scene.unit_settings
    return bpy.utils.units.to_string(us.system, 'LENGTH', value * us.scale_length, precision=3)


def _vector_row(layout, owner, attr, label):
    """Maya AE float3 row: label, then the three fields side by side."""
    split = layout.split(factor=0.3, align=True)
    split.label(text=label)
    split.row(align=True).prop(owner, attr, text="")


def _maya_number_rows(layout, context, ob):
    """Translate / Rotate / Scale as Maya number fields (no unit, never cut to "62 c", #85): the Channel Box text
    proxies, when ``ob`` is the lead and the only selected node (the proxies type into every selected node, the AE
    edits one). False when that doesn't apply."""
    if channel_box.is_bone(ob) or ob is not channel_box.lead(context) or len(channel_box.targets(context)) != 1:
        return False
    if ob.rotation_mode in {'QUATERNION', 'AXIS_ANGLE'}:
        return False
    cb = context.scene.allset_cb
    col = layout.column(align=True)
    for label, keys in (("Translate", ("tx", "ty", "tz")), ("Rotate", ("rx", "ry", "rz")),
                        ("Scale", ("sx", "sy", "sz"))):
        split = col.split(factor=0.3, align=True)
        split.label(text=label)
        row = split.row(align=True)
        for key in keys:
            # each field its own cell: the Channel Box key colours (keyed / animated / driven / muted) and lock
            cell = row.row(align=True)
            cell.alert = channel_box.state_alert(channel_box.channel_state(ob, key))
            cell.enabled = not channel_box.is_locked(ob, key)
            cell.prop(cb, key + "_text", text="")
    return True


def draw_transform_channels(layout, context, ob):
    if _maya_number_rows(layout, context, ob):
        return
    col = layout.column(align=True)
    _vector_row(col, ob, "location", "Translate")
    if ob.rotation_mode == 'QUATERNION':
        _vector_row(col, ob, "rotation_quaternion", "Rotate")
    elif ob.rotation_mode == 'AXIS_ANGLE':
        _vector_row(col, ob, "rotation_axis_angle", "Rotate")
    else:
        _vector_row(col, ob, "rotation_euler", "Rotate")
    _vector_row(col, ob, "scale", "Scale")


def draw_world_pivot(layout, context, ob):
    col = layout.column(align=True)
    for axis, value in zip("XYZ", ob.matrix_world.translation):
        col.label(text=f"World Rotate Pivot {axis}: {_length(context, value)}")


LIMIT_PROPS = {
    'LIMIT_LOCATION': ("use_min_{a}", "min_{a}", "use_max_{a}", "max_{a}"),
    'LIMIT_SCALE': ("use_min_{a}", "min_{a}", "use_max_{a}", "max_{a}"),
    'LIMIT_ROTATION': ("use_limit_{a}", "min_{a}", "max_{a}"),
}


def draw_limit(layout, context, ob, kind):
    con = next((c for c in ob.constraints if c.type == kind), None)
    if con is None:
        layout.operator("allset.ae_add_limit", text=f"Add {kind.replace('_', ' ').title()}").type = kind
        return
    for a in "xyz":
        row = layout.row(align=True)
        for pattern in LIMIT_PROPS[kind]:
            row.prop(con, pattern.format(a=a))


def draw_visibility(layout, context, ob):
    if channel_box.is_bone(ob):
        layout.prop(ob.bone, "hide", text="Visibility", invert_checkbox=True)
    else:
        layout.prop(ob, "hide_viewport", text="Visibility", invert_checkbox=True)


JOINT_AXIS_NOTE = "Bone Y points to the child joint (Maya Primary Axis X)"


def joint_orient(pb):
    """Maya jointOrient (radians, xyz) from the joints' Maya frames (bone axes turned by
    ``allset_maya_frame``; a top joint in Maya's world axes)."""
    from ..operators import joints
    bone = pb.bone
    frame = joints.maya_bone_frame(bone)
    parent = joints.maya_bone_frame(bone.parent) if bone.parent is not None else joints.armature_world(pb.id_data)
    return (parent.transposed() @ frame).to_euler('XYZ')


def draw_joint_orient(layout, context, pb):
    split = layout.split(factor=0.3, align=True)
    split.label(text="Joint Orient")
    row = split.row(align=True)
    for v in joint_orient(pb):
        row.label(text=cb_entry.fmt_number(math.degrees(v)))   # Maya numbers: no "-0"
    from . import notices
    notices.tip(row, JOINT_AXIS_NOTE)    # a tooltip, not a Blender sentence in the AE


def draw_joint_stiffness(layout, context, pb):
    split = layout.split(factor=0.3, align=True)
    split.label(text="Stiffness")
    row = split.row(align=True)
    for a in "xyz":
        row.prop(pb, f"ik_stiffness_{a}", text="")


def draw_shading(layout, context, ob):
    row = layout.row(align=True)
    row.operator("object.shade_smooth", text="Soften (Smooth)")
    row.operator("object.shade_flat", text="Harden (Flat)")
    layout.operator("object.shade_auto_smooth", text="Soften by Angle")


def draw_smooth_mesh(layout, context, ob):
    row = layout.row(align=True)
    for level, label in ((1, "1 Off"), (2, "2 Cage"), (3, "3 Smooth")):
        row.operator("allset.smooth_preview", text=label).level = level
    sub = display.preview_modifier(ob, create=False)
    if sub is not None:
        layout.prop(sub, "levels", text="Division Levels")
        layout.prop(sub, "render_levels", text="Render Levels")


def draw_light_decay(layout, context, ob):
    """Maya Decay Rate (operators/lights.py); where the render can't follow it, the tooltip says why."""
    from ..operators import lights
    from . import notices
    light = getattr(ob, "data", None)
    if light is None or not hasattr(light, "allset_decay"):
        return
    row = layout.row(align=True)
    row.prop(light, "allset_decay", text=attr_label(context, "Decay Rate", "decayRate"))
    notices.tip(row, lights.decay_notice(light))


def draw_type_manipulator(layout, context, ob):
    """Type Manipulator on / off for this type, and putting characters back (operators/type_manip.py)."""
    from ..operators import type_manip
    if ob is None or ob.type != 'FONT':
        return
    on = type_manip.handle_of(ob) is not None
    row = layout.row(align=True)
    row.operator("allset.type_manipulator", text="Type Manipulator", depress=on)
    sub = row.row(align=True)
    sub.enabled = type_manip.modifier(ob) is not None
    sub.operator("allset.type_reset", text="Reset Character").all = False
    sub.operator("allset.type_reset", text="Reset All").all = True


DRAWERS = {"transform_channels": draw_transform_channels, "world_pivot": draw_world_pivot,
           "visibility": draw_visibility, "shading": draw_shading, "smooth_mesh": draw_smooth_mesh,
           "joint_orient": draw_joint_orient, "joint_stiffness": draw_joint_stiffness,
           "light_decay": draw_light_decay, "type_manipulator": draw_type_manipulator}


def attr_label(context, label, ident):
    """The row label for Display > Attribute Names: Nice (the label), Long (the property id), Short (its initials)."""
    mode = getattr(context.window_manager, "allset_ae_names", 'NICE')
    if mode == 'NICE' or not ident:
        return label
    if mode == 'LONG':
        return ident
    parts = [p for p in ident.split("_") if p]
    return "".join(p[0] for p in parts) if len(parts) > 1 else ident[:3]


def draw_row(layout, context, ob, target, row):
    kind = row[0]
    if kind == "prop":
        _k, owner_name, path, label = row
        owner, attr = resolve(_owner(context, ob, target, owner_name), path)
        if owner is not None and hasattr(owner, attr):
            layout.prop(owner, attr, text=attr_label(context, label, attr))
    elif kind == "draw":
        name = row[1]
        if name.startswith("limit:"):
            draw_limit(layout, context, ob, name[6:])
        else:
            DRAWERS[name](layout, context, ob)
    elif kind in {"socket", "maya"}:
        if kind == "maya":
            _k, maya_prop, label, socket = row
        else:
            _k, socket, label = row
            maya_prop = None
        from ..operators import material as _material
        # "Base Color" of a lambert-family material = its Maya Diffuse node's B (Maya Color)
        inp = _material.maya_input(target, socket)
        if inp is None:
            if maya_prop is not None and principled(target) is not None and hasattr(target, maya_prop):
                layout.prop(target, maya_prop, text=label)   # e.g. Diffuse 1.0 without the node; editing adds it
            return
        row = layout.row(align=True)
        if inp.is_linked:
            source = inp.links[0].from_node
            row.label(text=f"{label}: connected ({source.name})")
        elif maya_prop is not None and hasattr(target, maya_prop):
            row.prop(target, maya_prop, text=label)          # Maya's number, converted (#71)
        elif hasattr(inp, "default_value"):
            row.prop(inp, "default_value", text=label)
        else:
            row.label(text=label)
        # Maya's map (checker) button: Create Render Node / Break Connection (operators/shading_maps.py)
        op = row.operator("allset.ae_map", text="", icon='TEXTURE')
        op.material, op.socket = target.name, socket
        if inp.is_linked and source.type == 'TEX_IMAGE':
            # Maya file node's Image Name with its folder button
            layout.template_ID(source, "image", new="image.new", open="image.open")
    elif kind == "missing":
        _k, label, note = row
        sub = layout.row()
        sub.enabled = False
        sub.label(text=f"{label}: {note}")


SECTION_INDENT = 1.2     # separator factor in front of an open section's content area (under the header arrow)


def section_body(body):
    """The content of an open Attribute Editor section: Maya draws it inset under the section header, in a content
    area of its own shade (2 px in from each side, one step off the editor's grey;
    #194). The box starts under the section's disclosure arrow, gives the content area its shade and frame; the
    column is what the rows go into."""
    row = body.row()
    row.separator(factor=SECTION_INDENT)
    return row.box().column()


def draw_sections(layout, context, ob, target, sections, layout_id, prefix=""):
    for sec in sections:
        header, body = layout.panel(f"allset_ae_{layout_id}_{prefix}{sec.name}",
                                    default_closed=not sec.open)
        header.label(text=sec.name)
        if body is None:
            continue
        col = section_body(body)
        for row in sec.rows:
            draw_row(col, context, ob, target, row)
        if sec.subs:
            draw_sections(col, context, ob, target, sec.subs, layout_id, f"{prefix}{sec.name}/")


# RNA properties of every modifier that are not the node's own attributes.
_MOD_SKIP = {"rna_type", "name", "type", "show_viewport", "show_render", "show_in_editmode",
             "show_on_cage", "show_expanded", "is_active", "is_override_data_editable",
             "use_apply_on_spline", "use_pin_to_last", "persistent_uid", "execution_time"}


def modifier_props(md):
    out = []
    for p in md.bl_rna.properties:
        ident = p.identifier
        if ident in _MOD_SKIP or p.is_readonly or p.type == 'COLLECTION' or ident.startswith("open_"):
            continue
        out.append(ident)
    return out


def draw_history(layout, context, ob, md):
    header, body = layout.panel(f"allset_ae_history_{md.type}", default_closed=False)
    header.label(text=f"{nice_type(modifier_node(ob, md)[1])} History")
    if body is not None:
        col = section_body(body)
        col.prop(md, "show_viewport", text="Enabled (Node State)")
        from ..operators import deformers_205a, deformers_205b, sweep_mesh
        # Tension / Solidify / Sculpt, Morph / Jiggle and sweepMeshCreator draw their Maya attributes
        drawn = deformers_205a.draw_ae(col, md) or deformers_205b.draw_ae(col, md) or sweep_mesh.draw_ae(col, md)
        if md.type == 'ARMATURE' and hasattr(ob, "allset_skinning_method"):
            col.prop(ob, "allset_skinning_method")       # Maya skinCluster Skinning Method
        for ident in ([] if drawn else modifier_props(md)):
            col.prop(md, ident, text=attr_label(context, md.bl_rna.properties[ident].name, ident))
    row = layout.row(align=True)
    op = row.operator("allset.ae_modifier", text="Delete History")
    op.modifier, op.action = md.name, 'APPLY'
    op = row.operator("allset.ae_modifier", text="Delete", icon='X')
    op.modifier, op.action = md.name, 'REMOVE'


# Constraint properties that are not the Maya constraint node's own attributes.
_CON_SKIP = {"rna_type", "name", "type", "show_expanded", "is_valid", "active", "is_override_data_editable",
             "is_override_data_local", "mute", "enabled", "influence", "error_location", "error_rotation"}


def constraint_props(con):
    return [p.identifier for p in con.bl_rna.properties
            if p.identifier not in _CON_SKIP and not p.is_readonly and p.type != 'COLLECTION']


def draw_constraint(layout, context, node, con):
    """A Maya constraint node tab: target weight (= influence), then the constraint's settings."""
    header, body = layout.panel(f"allset_ae_constraint_{con.type}", default_closed=False)
    header.label(text=f"{channel_box.maya_constraint_type(con, con.type.title())} Attributes")
    if body is not None:
        col = section_body(body)
        if hasattr(con, "enabled"):
            col.prop(con, "enabled", text="Enabled (Node State)")
        col.prop(con, "influence", text=channel_box.weight_name(con))
        for ident in constraint_props(con):
            col.prop(con, ident, text=attr_label(context, con.bl_rna.properties[ident].name, ident))


def draw_extra(layout, owner, layout_id):
    keys = [k for k in owner.keys() if not k.startswith(("_", "allset_", "cycles"))]
    header, body = layout.panel(f"allset_ae_{layout_id}_extra", default_closed=True)
    header.label(text="Extra Attributes")
    if body is None:
        return
    body = section_body(body)
    if not keys:
        body.label(text="(none)")
    for k in sorted(keys):
        body.prop(owner, f'["{k}"]', text=k)


def draw_extrude_history(layout, context, rec):
    """The polyExtrudeFace tab: Maya's "Poly Extrude Face History" with the kit record's values (the same text
    proxies as Channel Box INPUTS, ui/in_view.py); also polyExtrudeEdge / Vertex and polyBevel3."""
    header, body = layout.panel("allset_ae_history_extrude", default_closed=False)
    header.label(text=f"{nice_type(rec.spec.node_type)} History")
    if body is None:
        return
    hist = context.window_manager.allset_history
    col = section_body(body).column(align=True)
    from . import node_attributes
    node = node_attributes.for_record(context, ae_node(context), rec)
    for field in rec.spec.fields:
        split = col.split(factor=0.42, align=True)
        split.label(text=attr_label(context, rec.spec.labels[field], field))
        cell = split.row()
        cell.enabled = node is not None and node_attributes.editable(node, field)
        cell.prop(hist, f"{field}_text", text="")
    if rec.spec.kind == 'BRIDGE':
        from . import bridge_editor
        bridge_editor.draw_controls(col, node)


def content_width(context):
    """Px the dock's panel content spans: region minus Blender's panel margins and the Maya tab strip."""
    region = getattr(context, "region", None)
    if region is None or region.width <= 1:
        return None
    from . import maya_dock
    scale = context.preferences.system.ui_scale or 1.0
    unit = maya_dock._ui_unit(scale, context.preferences.system.pixel_size or 1.0)
    return region.width - 2 * maya_dock.PANEL_MARGIN_U * unit - maya_dock.area_reserved_px(context) - 4 * scale


def text_widths(context, labels, extra_units=None):
    """Px a button needs for each label: the text (Blender's UI font size) plus its margins (0.4 widget unit a side)
    and ``extra_units`` widget units (a menu's arrow)."""
    from . import maya_dock
    scale = context.preferences.system.ui_scale or 1.0
    unit = maya_dock._ui_unit(scale, context.preferences.system.pixel_size or 1.0)
    extra_units = extra_units or [0.0] * len(labels)
    try:
        import blf
        blf.size(0, 11 * scale)
        text = [blf.dimensions(0, t)[0] for t in labels]
    except Exception:
        text = [len(t) * 7 * scale for t in labels]
    return [w + (1.0 + e) * unit for w, e in zip(text, extra_units)]


def wrap_rows(context, labels, equal=True, extra_units=None):
    """``labels`` split into rows that each fit the dock, so no tab / button / menu text is cut ("pCubeS...",
    "Sele...", #104). Maya's AE is wider and scrolls its tab bar; the kit dock can be
    narrower (event-simulated sessions don't fit it, users drag it): rows wrap like a narrow Qt bar.
    ``equal``: an aligned row gives every button the same width, so a row needs n × its widest label; else the
    labels keep their natural widths (left / right aligned rows). Without a region (tests with a fake layout) one
    row."""
    avail = content_width(context) if labels else None
    if avail is None:
        return [list(range(len(labels)))]
    widths = text_widths(context, labels, extra_units)
    rows, cur = [], []
    for i in range(len(labels)):
        trial = cur + [i]
        need = len(trial) * max(widths[j] for j in trial) if equal else sum(widths[j] for j in trial)
        if cur and need > avail:
            rows.append(cur)
            trial = [i]
        cur = trial
    rows.append(cur)
    return rows


def tab_window(widths, avail, current, arrows):
    """Maya's AE tab bar is one Qt tab row that scrolls (audit 16 G1): the tabs
    [a, b) shown, ``current`` among them, as many as fit in ``avail`` px; when not all fit, ``arrows`` px are kept
    for the ◀ ▶ buttons. Returns (a, b, overflow). Pure (tests/test_step211_fix_batch.py)."""
    n = len(widths)
    if avail is None or sum(widths) <= avail:
        return 0, n, False
    room = avail - arrows
    a = b = min(max(current, 0), n - 1)
    used = widths[a]
    b += 1
    while True:
        grew = False
        if b < n and used + widths[b] <= room:
            used += widths[b]
            b += 1
            grew = True
        if a > 0 and used + widths[a - 1] <= room:
            a -= 1
            used += widths[a]
            grew = True
        if not grew:
            return a, b, True


def draw_tab_strip(layout, context, ob, current):
    """One row of tabs at their text width, left-aligned like Maya's; a dock too narrow for all of them shows the
    ones around the current tab with ◀ ▶ (previous / next tab; Qt's arrows only scroll)."""
    items = tabs(ob)
    labels = [label for _k, label, _t in items]
    keys = [k for k, _l, _t in items]
    cur = keys.index(current) if current in keys else 0
    avail = content_width(context) if labels else None
    if avail is None:
        a, b, over = 0, len(items), False
        widths = None
    else:
        from . import maya_dock
        scale = context.preferences.system.ui_scale or 1.0
        unit = maya_dock._ui_unit(scale, context.preferences.system.pixel_size or 1.0)
        widths = text_widths(context, labels)
        a, b, over = tab_window(widths, avail, cur, 2 * unit)
    row = layout.row(align=True)
    if widths is not None:
        row.alignment = 'LEFT'
    if over:
        prev = row.row(align=True)
        prev.enabled = cur > 0
        prev.operator("allset.ae_tab", text="", icon='TRIA_LEFT').key = keys[max(cur - 1, 0)]
    for i in range(a, b):
        cell = row.row(align=True)
        if widths is not None:
            cell.ui_units_x = widths[i] / unit
        cell.operator("allset.ae_tab", text=labels[i], depress=(keys[i] == current)).key = keys[i]
    if over:
        nxt = row.row(align=True)
        nxt.enabled = cur < len(keys) - 1
        nxt.operator("allset.ae_tab", text="", icon='TRIA_RIGHT').key = keys[min(cur + 1, len(keys) - 1)]


def draw(layout, context, ob):
    """The whole Attribute Editor for ``ob`` (also used by tests with a fake layout)."""
    key = current_tab(context, ob)
    draw_tab_strip(layout, context, ob, key)
    target = tab_target(ob, key)
    if target is None:
        return
    entry = next(t for t in tabs(ob) if t[0] == key)
    draw_head(layout, context, ob, key, target, entry)
    kind = _kind(key)
    if kind == "SG":
        draw_shading_group(layout, key, target)
    elif kind == "C":
        draw_constraint(layout, context, ob, target)
    elif kind == "H":
        draw_extrude_history(layout, context, target)
    elif kind == "CH":
        from . import creation_inputs
        creation_inputs.draw_ae(layout, context, ob)
    elif kind == "M":
        draw_history(layout, context, ob, target)
    else:
        sections, layout_id = sections_for(ob, key)
        draw_sections(layout, context, ob, target, sections, layout_id or "data")
        if isinstance(target, (bpy.types.ID, bpy.types.PoseBone)):
            draw_extra(layout, target, layout_id or "data")
    draw_notes(layout, context, ob, key, entry)
    draw_bottom(layout, context)


def draw_head(layout, context, ob, key, target, entry):
    """Maya's node row: "<type>: [name]" with the in / out arrows, Focus / Presets, Show / Hide
    (tooltips as Maya's)."""
    kind = _kind(key)
    top = layout.row(align=True)
    head = top.row(align=True)
    head.label(text=f"{entry[2]}:")
    if kind in ("SG", "H", "CH"):
        head.label(text=entry[1])
    elif kind == "M" and entry[1] != target.name:
        head.label(text=entry[1])           # the Maya node name (polyBevel31); renaming keeps Blender's name
    else:
        head.prop(target, "name", text="")
    if kind in ("M", "H", "CH"):
        sub = head.row(align=True)
        sub.operator("allset.ae_step", text="", icon='TRIA_LEFT').forward = False
        sub.operator("allset.ae_step", text="", icon='TRIA_RIGHT').forward = True
    # Maya puts Focus / Presets and Show / Hide right of the name field; the narrow dock gets them as one row
    # under it, right-aligned
    buttons = (("op", "allset.ae_focus", "Focus"), ("menu", "ALLSET_MT_ae_presets", "Presets"),
               ("op", "allset.ae_show_types", "Show"), ("op", "allset.ae_hide_type", "Hide"))
    for idx in wrap_rows(context, [b[2] for b in buttons], equal=False,
                         extra_units=[1.0 if b[0] == "menu" else 0.0 for b in buttons]):
        row = layout.row(align=True)
        row.alignment = 'RIGHT'
        for i in idx:
            kind, ident, text = buttons[i]
            if kind == "menu":
                row.menu(ident, text=text)
            else:
                row.operator(ident, text=text)
    return head


NOTES_PROP = "allset_notes"


def notes_owner(ob, key):
    """(ID-property owner, key) where the Notes of a tab live: the node's own datablock / pose bone, or for
    history / constraint nodes (no ID properties in Blender) the object under ``allset_notes:<tab>``."""
    if ob is None:
        return None, NOTES_PROP
    target = tab_target(ob, key)
    if isinstance(target, (bpy.types.ID, bpy.types.PoseBone)):
        return target, NOTES_PROP
    return ob, f"{NOTES_PROP}:{key}"


def _current_node(context):
    ob = ae_node(context)
    return (ob, current_tab(context, ob)) if ob is not None else (None, "")


def _notes_get(_self):
    try:
        ob, key = _current_node(bpy.context)
        owner, prop = notes_owner(ob, key)
        value = owner.get(prop, "") if owner is not None else ""
        return value if isinstance(value, str) else ""
    except (AttributeError, ReferenceError, KeyError):
        return ""


def _notes_set(_self, value):
    ob, key = _current_node(bpy.context)
    owner, prop = notes_owner(ob, key)
    if owner is None:
        return
    if value:
        owner[prop] = value
    elif prop in owner.keys():
        del owner[prop]


def draw_notes(layout, context, ob, key, entry):
    """Maya's Notes box under the sections (Show > Show Notes)."""
    if not context.window_manager.allset_ae_show_notes:
        return
    layout.separator()
    layout.label(text=f"Notes:  {entry[1]}")
    layout.prop(context.scene, "allset_ae_notes", text="")


BOTTOM = (("allset.ae_select", "Select"), ("allset.ae_load", "Load Attributes"), ("allset.ae_copy_tab", "Copy Tab"))


def draw_bottom(layout, context=None):
    """Maya's bottom buttons: Select, Load Attributes, Copy Tab (wrapped when the dock is too narrow)."""
    layout.separator()
    col = layout.column(align=True)
    groups = wrap_rows(context, [t for _o, t in BOTTOM]) if context is not None else [list(range(len(BOTTOM)))]
    for idx in groups:
        row = col.row(align=True)
        for i in idx:
            row.operator(BOTTOM[i][0], text=BOTTOM[i][1])


def draw_shading_group(layout, key, mat):
    """Maya's shading group tab (AEshadingEngineTemplate: Shading Group Attributes): the surface material opens
    its own tab; Blender has no volume / displacement slots of their own on a shading group."""
    header, box = layout.panel("ae_shading_group", default_closed=False)
    header.label(text="Shading Group Attributes")
    if box is None:
        return
    box = section_body(box)
    row = box.row(align=True)
    row.label(text="Surface Material")
    row.operator("allset.ae_tab", text=mat.name, icon='MATERIAL').key = "MAT:" + key.split(":", 1)[1]
    for label in ("Volume Material", "Displacement Mat."):
        row = box.row(align=True)
        row.active = False
        row.label(text=label)
        row.label(text="")


# --- operators -----------------------------------------------------------------------------

def set_tab(context, key):
    wm = context.window_manager
    wm.allset_ae_tab = key
    wm.allset_ae_kind = _kind(key)
    if _kind(key) == 'H':
        from ..operators import model_history
        ob = ae_node(context)
        target = tab_target(ob, key) if ob is not None else None
        if target is not None:
            model_history.activate(ob, getattr(target, 'history_id', None) or target.name)


class ALLSET_OT_ae_tab(bpy.types.Operator):
    """Show this node in the Attribute Editor"""
    bl_idname = "allset.ae_tab"
    bl_label = "Attribute Editor Tab"
    bl_options = {'INTERNAL'}

    key: StringProperty()

    def execute(self, context):
        set_tab(context, self.key)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_ae_step(bpy.types.Operator):
    """Go to the next input (left) or output (right) node in the history (Maya in/out arrows)"""
    bl_idname = "allset.ae_step"
    bl_label = "Input / Output Node"
    bl_options = {'INTERNAL'}

    forward: bpy.props.BoolProperty()

    def execute(self, context):
        ob = ae_node(context)
        if ob is None:
            return {'CANCELLED'}
        keys = [t[0] for t in tabs(ob) if _kind(t[0]) in ("H", "M", "CH")]
        cur = current_tab(context, ob)
        if cur not in keys:
            return {'CANCELLED'}
        i = keys.index(cur) + (1 if self.forward else -1)
        if 0 <= i < len(keys):
            set_tab(context, keys[i])
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_ae_modifier(bpy.types.Operator):
    """Delete History: apply this modifier (keep its effect, drop the node); Delete: remove it"""
    bl_idname = "allset.ae_modifier"
    bl_label = "History Node"
    bl_options = {'REGISTER', 'UNDO'}

    modifier: StringProperty()
    action: EnumProperty(items=(('APPLY', "Apply", ""), ('REMOVE', "Remove", "")))

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None

    def execute(self, context):
        ob = context.active_object
        md = ob.modifiers.get(self.modifier)
        if md is None:
            return {'CANCELLED'}
        if self.action == 'REMOVE':
            ob.modifiers.remove(md)
            return {'FINISHED'}
        with context.temp_override(object=ob, active_object=ob):
            return bpy.ops.object.modifier_apply(modifier=self.modifier)


class ALLSET_OT_ae_add_limit(bpy.types.Operator):
    """Add a limit constraint (Maya Limit Information)"""
    bl_idname = "allset.ae_add_limit"
    bl_label = "Add Limit"
    bl_options = {'REGISTER', 'UNDO'}

    type: EnumProperty(items=[(k, k.replace('_', ' ').title(), "") for k in LIMIT_PROPS])

    @classmethod
    def poll(cls, context):
        return channel_box.lead(context) is not None

    def execute(self, context):
        con = channel_box.lead(context).constraints.new(self.type)   # a joint: the pose bone
        con.owner_space = 'LOCAL'   # Maya limits act on the channel values
        return {'FINISHED'}


class ALLSET_OT_ae_select(bpy.types.Operator):
    """Select only the node shown in the Attribute Editor"""
    bl_idname = "allset.ae_select"
    bl_label = "Select"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and ae_node(context) is not None

    def execute(self, context):
        ob = ae_node(context)
        if channel_box.is_bone(ob):
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        try:
            ob.select_set(True)
        except RuntimeError:     # not in the view layer
            return {'CANCELLED'}
        context.view_layer.objects.active = ob
        return {'FINISHED'}


def show_dock(context, dock):
    """Raise ``dock`` in the Maya tab stack, or open it as a floating window (ui/maya_dock.py)."""
    from . import maya_dock
    return maya_dock.show(context, dock)


class ALLSET_OT_ae_toggle(bpy.types.Operator):
    """Switch the dock between Channel Box / Layer Editor and Attribute Editor
    (Maya Ctrl+A)"""
    bl_idname = "allset.ae_toggle"
    bl_label = "Attribute Editor / Channel Box"

    def execute(self, context):
        wm = context.window_manager
        show_dock(context, 'CHANNEL_BOX' if wm.allset_dock == 'ATTRIBUTE_EDITOR' else 'ATTRIBUTE_EDITOR')
        return {'FINISHED'}


class ALLSET_OT_dock_show(bpy.types.Operator):
    """Show the Attribute Editor, the Channel Box / Layer Editor or the Modeling Toolkit: the tab stack's tab, or a
    floating window when the layout has no tab stack (Maya Windows > General Editors)"""
    bl_idname = "allset.dock_show"
    bl_label = "Show Dock Editor"

    dock: EnumProperty(items=DOCK_ITEMS, name="Editor")
    le_tab: bpy.props.StringProperty(name="Layer Editor Tab", options={'SKIP_SAVE', 'HIDDEN'},
                                     description="DISPLAY / ANIM: the Layer Editor tab to raise")

    def execute(self, context):
        show_dock(context, self.dock)
        if self.le_tab in ('DISPLAY', 'ANIM'):
            context.window_manager.allset_le_tab = self.le_tab
        return {'FINISHED'}


class ALLSET_OT_object_attributes(bpy.types.Operator):
    """Show this object in the Attribute Editor (Maya RMB marking menu row
    "<object>...")"""
    bl_idname = "allset.object_attributes"
    bl_label = "Object Attributes"

    rmb: bpy.props.BoolProperty(options={'HIDDEN', 'SKIP_SAVE'},
                                description="The object the RMB menu was opened on")

    @staticmethod
    def _object(context, rmb):
        if rmb:
            ob = bpy.data.objects.get(getattr(context.window_manager, "allset_mm_target", ""))
            if ob is not None:
                return ob
        return context.active_object

    @classmethod
    def poll(cls, context):
        return cls._object(context, True) is not None

    def execute(self, context):
        ob = self._object(context, self.rmb)
        if ob is None:
            return {'CANCELLED'}
        if context.active_object is not ob:
            try:   # Maya shows the node without changing the selection; the AE here shows the active object
                ob.select_get(view_layer=context.view_layer)
                context.view_layer.objects.active = ob
            except RuntimeError:
                return {'CANCELLED'}
        return bpy.ops.allset.dock_show(dock='ATTRIBUTE_EDITOR')


def _redraw(context):
    """The dock areas (Properties editors, any window) and the 3D Views."""
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in {'VIEW_3D', 'PROPERTIES'}:
                area.tag_redraw()


# --- panels ----------------------------------------------------------------------------------

# --- dock state --------------------------------------------------------------------
# WindowManager.allset_dock = the tab the Maya tab stack shows (Channel Box / Layer Editor, Attribute Editor,
# Modeling Toolkit; ui/maya_dock.py). The stack is its own area and simply redraws.


def _dock_update(self, context):
    from . import maya_dock
    maya_dock.redraw()


def draw_panel(layout, context):
    """The Attribute Editor body of the dock (``channel_box.ALLSET_PT_dock_attribute_editor``)."""
    if channel_box.placing_joints(context):
        from . import chrome
        chrome.wrapped(layout, channel_box.PLACING_TEXT)
        return
    from . import chrome
    # the dock is narrower than Maya's AE: the bar wraps where it would cut a menu name
    for idx in wrap_rows(context, [label for label, _m in MENU_BAR], equal=False):
        chrome.menu_bar(layout, [MENU_BAR[i] for i in idx])
    ob = ae_node(context)
    if ob is None:
        layout.label(text="make a selection")
        return
    _remember(ob)
    draw(layout, context, ob)


# --- Maya AE chrome ---------------------------------------------------------------------------------
# Menus, buttons and tooltips like Maya 2022's Attribute Editor (bars, widgets).

ATTRIBUTE_NAMES = (('NICE', "Nice", "Readable names (Translate X)"),
                   ('LONG', "Long", "Property names (location)"),
                   ('SHORT', "Short", "Abbreviated property names"))
AE = "Attribute Editor"
AE_NOTICES = {
    f"{AE}/Presets": ("Blender presets per tool", "Attribute presets of a node aren't kept by Blender"),
    f"{AE}/List/Selected Items": ("Selected menu", "The Selected menu lists the selection"),
    f"{AE}/List/Dynamics": ("Outliner", "Node lists by type: use the Outliner filter (Maya greys these too while "
                                         "Auto Load is on)"),
    f"{AE}/Show/Filters": ("Hide button", "Hide a node type with the Hide button, bring them back with Show"),
    f"{AE}/Show/Views": ("one view", "Blender has no alternative AE layouts (views / templates)"),
    f"{AE}/Help": ("Blender manual", "Help > Manual in Blender's menus; hover a field for its tooltip"),
}
_recent = []            # object names the AE showed, newest first (Focus menu)
RECENT = 8


def fits(context, entries):
    """True when a flat menu bar of ``entries`` fits the region (about 7 px a character + 14 px a menu at UI
    scale 1; region width unknown -> True)."""
    region = getattr(context, "region", None)
    if region is None or region.width <= 1:
        return True
    scale = context.preferences.system.ui_scale or 1.0
    need = sum(len(label) * 7 + 14 for label, _m in entries) * scale
    from . import maya_dock     # the dock's vertical tab strip takes the right edge
    return need <= region.width - 20 * scale - maya_dock.area_reserved_px(context)


def ae_node(context):
    """The object (or pose bone) the AE shows: the lead, or the focused node while Auto Load is off."""
    wm = context.window_manager
    if not getattr(wm, "allset_ae_auto_load", True):
        ob = bpy.data.objects.get(getattr(wm, "allset_ae_node", ""))
        if ob is not None:
            return ob
    return channel_box.lead(context)


def _remember(ob):
    name = getattr(ob, "name", None)
    if not name or (_recent and _recent[0] == name):
        return
    if name in _recent:
        _recent.remove(name)
    _recent.insert(0, name)
    del _recent[RECENT:]


def _greyed(layout, path, text):
    layout.operator("allset.menu_unavailable", text=text).item = f"{AE}/{path}"


class ALLSET_MT_ae_list(bpy.types.Menu):
    bl_label = "List"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        layout.prop(wm, "allset_ae_auto_load")
        row = layout.row()
        row.enabled = not wm.allset_ae_auto_load      # Maya greys it while Auto Load is on (ae bars)
        row.operator("allset.ae_load", text="Load Selected Attributes")
        _greyed(layout, "List/Selected Items", "Selected Items")
        layout.separator()
        for name in ("Dynamics", "Kinematics", "Deformers", "Lights", "Shading"):
            _greyed(layout, "List/Dynamics", name)


class ALLSET_MT_ae_selected(bpy.types.Menu):
    bl_label = "Selected"

    def draw(self, context):
        obs = list(getattr(context, "selected_objects", ()) or ())
        if not obs:
            self.layout.label(text="Nothing selected")
        for ob in obs:
            self.layout.operator("allset.ae_show_node", text=ob.name).name = ob.name


class ALLSET_MT_ae_focus(bpy.types.Menu):
    bl_label = "Focus"

    def draw(self, context):
        names = [n for n in _recent if n in bpy.data.objects]
        if not names:
            self.layout.label(text="No nodes yet")
        for name in names:
            self.layout.operator("allset.ae_show_node", text="|" + name).name = name


class ALLSET_MT_ae_attributes(bpy.types.Menu):
    bl_label = "Attributes"

    def draw(self, context):
        layout = self.layout
        layout.operator("allset.add_attribute", text="Add Attributes...")
        layout.operator("allset.delete_attribute", text="Delete Attributes...")
        layout.operator("allset.edit_attribute", text="Edit Attributes...")


class ALLSET_MT_ae_attribute_names(bpy.types.Menu):
    bl_label = "Attribute Names"

    def draw(self, context):
        self.layout.props_enum(context.window_manager, "allset_ae_names")


class ALLSET_MT_ae_display(bpy.types.Menu):
    bl_label = "Display"

    def draw(self, context):
        self.layout.menu(ALLSET_MT_ae_attribute_names.__name__)


class ALLSET_MT_ae_node_types(bpy.types.Menu):
    bl_label = "By Node Type"

    def draw(self, context):
        layout = self.layout
        layout.operator("allset.ae_show_types", text="Enable All")
        hidden = sorted(hidden_types(context))
        if hidden:
            layout.separator()
        for t in hidden:
            op = layout.operator("allset.ae_show_types", text=t, icon='CHECKBOX_DEHLT')
            op.node_type = t


class ALLSET_MT_ae_show(bpy.types.Menu):
    bl_label = "Show"

    def draw(self, context):
        layout = self.layout
        layout.menu(ALLSET_MT_ae_node_types.__name__)
        layout.separator()
        for text in ("Add New Filter Type...", "Add Filter Types for Selected", "Save Show Preset"):
            _greyed(layout, "Show/Filters", text)
        layout.separator()
        for text in ("Set Current View", "Set Global View"):
            _greyed(layout, "Show/Views", text)
        layout.prop(context.window_manager, "allset_ae_show_notes")


class ALLSET_MT_ae_help(bpy.types.Menu):
    bl_label = "Help"

    def draw(self, context):
        layout = self.layout
        _greyed(layout, "Help", "Help on Attribute Editor")
        ob = ae_node(context)
        if ob is not None:
            layout.separator()
            for t in sorted({t[2] for t in tabs(ob)}):
                _greyed(layout, "Help", f'Help on "{t}"')
        layout.separator()
        _greyed(layout, "Help", "Node and Attribute Reference")


class ALLSET_MT_ae_presets(bpy.types.Menu):
    bl_label = "Presets"

    def draw(self, context):
        for text in ("Save attribute preset...", "Edit Presets..."):
            _greyed(self.layout, "Presets", text)


MENU_BAR = (("List", "ALLSET_MT_ae_list"), ("Selected", "ALLSET_MT_ae_selected"), ("Focus", "ALLSET_MT_ae_focus"),
            ("Attributes", "ALLSET_MT_ae_attributes"), ("Display", "ALLSET_MT_ae_display"),
            ("Show", "ALLSET_MT_ae_show"), ("Help", "ALLSET_MT_ae_help"))
MENUS = (ALLSET_MT_ae_list, ALLSET_MT_ae_selected, ALLSET_MT_ae_focus, ALLSET_MT_ae_attributes,
         ALLSET_MT_ae_attribute_names, ALLSET_MT_ae_display, ALLSET_MT_ae_node_types, ALLSET_MT_ae_show,
         ALLSET_MT_ae_help, ALLSET_MT_ae_presets)


class ALLSET_OT_ae_focus(bpy.types.Operator):
    """Set Attribute Editor focus to this node (it stays on this node and tab; List > Auto Load Selected
    Attributes follows the selection again)"""
    bl_idname = "allset.ae_focus"
    bl_label = "Focus"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        ob = ae_node(context)
        if ob is None or channel_box.is_bone(ob):
            return {'CANCELLED'}
        wm = context.window_manager
        set_tab(context, current_tab(context, ob))
        wm.allset_ae_node = ob.name
        wm.allset_ae_auto_load = False
        _remember(ob)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_ae_show_types(bpy.types.Operator):
    """Show all the related nodes in the attribute editor"""
    bl_idname = "allset.ae_show_types"
    bl_label = "Show"
    bl_options = {'INTERNAL'}

    node_type: StringProperty(options={'SKIP_SAVE'}, description="Only this node type (empty: all)")

    def execute(self, context):
        wm = context.window_manager
        wm.allset_ae_hidden = ",".join(sorted(hidden_types(context) - {self.node_type})) if self.node_type else ""
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_ae_hide_type(bpy.types.Operator):
    """Hide nodes of this type in the attribute editor"""
    bl_idname = "allset.ae_hide_type"
    bl_label = "Hide"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        ob = ae_node(context)
        if ob is None:
            return {'CANCELLED'}
        key = current_tab(context, ob)
        if _kind(key) in ("T", "S", "J"):      # the node itself always keeps its tab
            results.result(self, "The transform and shape tabs stay")
            return {'CANCELLED'}
        mtype = next((t[2] for t in tabs(ob) if t[0] == key), None)
        wm = context.window_manager
        wm.allset_ae_hidden = ",".join(sorted(hidden_types(context) | {mtype}))
        set_tab(context, "S" if ob.data is not None else "T")
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_ae_load(bpy.types.Operator):
    """Load current selection into the Attribute Editor"""
    bl_idname = "allset.ae_load"
    bl_label = "Load Attributes"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        lead = channel_box.lead(context)
        wm = context.window_manager
        wm.allset_ae_node = getattr(lead, "name", "") if lead is not None and not channel_box.is_bone(lead) else ""
        if lead is not None:
            _remember(lead)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_ae_show_node(bpy.types.Operator):
    """Show this node in the Attribute Editor"""
    bl_idname = "allset.ae_show_node"
    bl_label = "Show Node"
    bl_options = {'INTERNAL'}

    name: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        ob = bpy.data.objects.get(self.name)
        if ob is None:
            return {'CANCELLED'}
        wm = context.window_manager
        if wm.allset_ae_auto_load:
            try:   # the AE follows the active object: make this one active, the selection stays
                ob.select_get(view_layer=context.view_layer)
                context.view_layer.objects.active = ob
            except RuntimeError:
                return {'CANCELLED'}
        else:
            wm.allset_ae_node = ob.name
        _remember(ob)
        _redraw(context)
        return {'FINISHED'}


# AE tab kind -> Properties tab of the Copy Tab window and the ID it pins
COPY_TABS = {"T": 'OBJECT', "S": 'DATA', "M": 'MODIFIER', "H": 'DATA', "CH": 'DATA', "C": 'CONSTRAINT', "MAT": 'MATERIAL',
             "SG": 'MATERIAL', "J": 'BONE'}


def copy_tab_target(ob, key):
    """(Properties tab, ID to pin) for Copy Tab."""
    kind = _kind(key)
    tab = COPY_TABS.get(kind, 'OBJECT')
    if channel_box.is_bone(ob):
        return tab, ob.id_data
    if kind == "S" and ob.data is not None:
        return tab, ob.data
    if kind in ("MAT", "SG"):
        return tab, ob       # the material tab of a pinned object shows its slots
    return tab, ob


class ALLSET_OT_ae_copy_tab(bpy.types.Operator):
    """Copy the contents of the current tab into a new floating window (a Properties editor pinned to it)"""
    bl_idname = "allset.ae_copy_tab"
    bl_label = "Copy Tab"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return ae_node(context) is not None and context.window is not None

    def execute(self, context):
        from ..operators.menu_extras import open_window
        ob = ae_node(context)
        tab, pin = copy_tab_target(ob, current_tab(context, ob))
        area = max(context.window.screen.areas, key=lambda a: a.width * a.height, default=None)
        new = open_window(context, area, "attribute_editor_copy") if area is not None else None
        if new is None:
            from . import window_places
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open a new window")
            return {'CANCELLED'}
        target = new.screen.areas[0]
        target.ui_type = 'PROPERTIES'
        state = {"n": 40}
        win_ptr, area_ptr = new.as_pointer(), target.as_pointer()

        def tick():
            target = live_refs.area(area_ptr, win_ptr)   # pointers, looked up each tick (#36)
            if target is None:
                return None
            try:
                space = target.spaces.active
                space.pin_id = pin
                space.use_pin_id = True
                space.context = tab
            except (TypeError, ReferenceError, AttributeError):
                state["n"] -= 1
                return 0.05 if state["n"] > 0 else None
            target.tag_redraw()
            return None
        bpy.app.timers.register(tick, first_interval=0.0)
        return {'FINISHED'}


classes = (ALLSET_OT_ae_tab, ALLSET_OT_ae_step, ALLSET_OT_ae_modifier, ALLSET_OT_ae_add_limit,
           ALLSET_OT_ae_select, ALLSET_OT_ae_toggle, ALLSET_OT_dock_show, ALLSET_OT_object_attributes,
           ALLSET_OT_ae_focus, ALLSET_OT_ae_show_types, ALLSET_OT_ae_hide_type, ALLSET_OT_ae_load,
           ALLSET_OT_ae_copy_tab, ALLSET_OT_ae_show_node) + MENUS


def register():
    wm = bpy.types.WindowManager
    wm.allset_dock = EnumProperty(name="Dock", items=DOCK_ITEMS, options={'SKIP_SAVE'}, update=_dock_update)
    wm.allset_ae_tab = StringProperty(options={'SKIP_SAVE'})
    wm.allset_ae_kind = StringProperty(default="S", options={'SKIP_SAVE'})
    wm.allset_ae_auto_load = bpy.props.BoolProperty(
        name="Auto Load Selected Attributes", default=True, options={'SKIP_SAVE'},
        description="The Attribute Editor follows the selection (off: it keeps showing its node)")
    wm.allset_ae_node = StringProperty(options={'SKIP_SAVE'})
    wm.allset_ae_hidden = StringProperty(options={'SKIP_SAVE'})
    wm.allset_ae_show_notes = bpy.props.BoolProperty(name="Show Notes", default=True, options={'SKIP_SAVE'})
    wm.allset_ae_names = EnumProperty(name="Attribute Names", items=ATTRIBUTE_NAMES, default='NICE',
                                        options={'SKIP_SAVE'})
    bpy.types.Scene.allset_ae_notes = StringProperty(
        name="Notes", get=_notes_get, set=_notes_set, options={'SKIP_SAVE'},
        description="Notes of the node shown (Maya's notes attribute; kept in the file)")
    from . import notices
    notices.PANEL_NOTICES.update(AE_NOTICES)
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    from . import notices
    for k in AE_NOTICES:
        notices.PANEL_NOTICES.pop(k, None)
    _recent.clear()
    del bpy.types.Scene.allset_ae_notes
    wm = bpy.types.WindowManager
    for name in ("allset_ae_names", "allset_ae_show_notes", "allset_ae_hidden", "allset_ae_node",
                 "allset_ae_auto_load"):
        delattr(wm, name)
    del wm.allset_ae_kind
    del wm.allset_ae_tab
    del wm.allset_dock
