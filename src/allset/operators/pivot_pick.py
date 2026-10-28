# SPDX-License-Identifier: GPL-3.0-or-later
"""Custom pivot component picking, in object mode and mesh component mode.

Maya 2026, Change the pivot point:
https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Basics/files/GUID-150B390E-840B-4FE3-B8E9-8DEBCE7CEC97.htm

Click: position + orientation; Shift: position only; Ctrl: orientation only;
Ctrl+Shift: aim the active pivot axis. Picking changes the pivot, never the mesh
selection. The existing pre-selection cache supplies occlusion-aware V/E/F hits.
"""

import bpy
from mathutils import Matrix, Vector

from . import hold, pivot, preselect


def axes_from(tangent, normal):
    """Right-handed world frame: X follows an edge/tangent, Z the surface normal."""
    z = Vector(normal)
    if z.length < 1e-9:
        z = Vector((0, 0, 1))
    z.normalize()
    x = Vector(tangent) - z * Vector(tangent).dot(z)
    if x.length < 1e-9:
        helper = min((Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))), key=lambda v: abs(v.dot(z)))
        x = helper - z * helper.dot(z)
    x.normalize()
    y = z.cross(x).normalized()
    return Matrix((x, y, z)).transposed()


def component_frame(ob, bm, kind, index):
    """World position/frame of a vertex, edge midpoint or face centre; no selection edits."""
    bm.normal_update()
    for elements in (bm.verts, bm.edges, bm.faces):
        elements.ensure_lookup_table()
    mw = ob.matrix_world
    normal_matrix = mw.to_3x3().inverted_safe().transposed()
    linear = mw.to_3x3()
    if kind == 'VERT':
        element = bm.verts[index]
        point, normal = element.co.copy(), element.normal.copy()
        edges = list(element.link_edges)
    elif kind == 'EDGE':
        element = bm.edges[index]
        point = (element.verts[0].co + element.verts[1].co) / 2
        normal = sum((f.normal for f in element.link_faces), Vector())
        edges = [element]
    elif kind == 'FACE':
        element = bm.faces[index]
        point, normal = element.calc_center_median(), element.normal.copy()
        edges = list(element.edges)
    else:
        raise ValueError("Unknown pivot component: " + kind)
    if edges:
        edge = max(edges, key=lambda e: (linear @ (e.verts[1].co-e.verts[0].co)).length_squared)
        tangent = linear @ (edge.verts[1].co-edge.verts[0].co)
    else:
        tangent = linear.col[0]
    return mw @ point, axes_from(tangent, normal_matrix @ normal)


def _current_frame(context):
    if context.mode == 'EDIT_MESH':
        return context.scene.cursor.location.copy(), context.scene.cursor.matrix.to_3x3()
    ob = context.active_object
    return ob.matrix_world.translation.copy(), pivot_axes(context, ob)


def pivot_axes(context, ob):
    return pivot.axes_for(ob)


def apply_component(context, point, axes, shift=False, ctrl=False):
    """Apply a picked component while respecting Maya's position/orientation options."""
    from .pivot_menu import option
    position = option("SNAP_POS", context) and not ctrl
    orientation = option("SNAP_ORI", context) and not shift
    if shift and ctrl:
        origin, current = _current_frame(context)
        direction = Vector(point)-origin
        if direction.length < 1e-9:
            return
        from ..ui import manipulator
        handle = manipulator._active_handle('TRANSLATE')
        constraint = (handle or {}).get("constraint_axis", ())
        axis = next((i for i, enabled in enumerate(constraint) if enabled), 0)
        axes = current.col[axis].rotation_difference(direction.normalized()).to_matrix() @ current
        position, orientation = False, True

    if context.mode == 'EDIT_MESH':
        cursor = context.scene.cursor
        location = Vector(point) if position else cursor.location.copy()
        rotation = axes if orientation else cursor.matrix.to_3x3()
        cursor.matrix = Matrix.Translation(location) @ rotation.to_4x4()
    else:
        from . import freeze
        pivot.process(context)
        for ob in freeze.parents_first(list(context.selected_objects)):
            if position:
                pivot.match_pivot(ob, point)
            if orientation:
                ob[pivot.PROP] = tuple(ob.matrix_world.to_quaternion().inverted() @ axes.to_quaternion())
            context.view_layer.update()
        if orientation:
            pivot.set_custom_orientation(context, axes)
        pivot.process(context)
    hold._redraw()


class ALLSET_OT_pivot_pick(bpy.types.Operator):
    """Place and align the custom pivot on a vertex, edge or face without changing the selection"""
    bl_idname = "allset.pivot_pick"
    bl_label = "Set Custom Pivot from Component"
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return (getattr(context.area, "type", None) == 'VIEW_3D'
                and context.region_data is not None and preselect.pivot_picking(context))

    def invoke(self, context, event):
        if event.alt or event.oskey:
            return {'PASS_THROUGH'}
        from .manip import from_xform_gizmo
        if from_xform_gizmo(context):
            return {'PASS_THROUGH'}
        region, rv3d = context.region, context.region_data
        mouse = (event.mouse_region_x, event.mouse_region_y)
        cs = preselect.caches(context)
        if preselect._handles_block(context, region, rv3d, mouse, cs):
            return {'PASS_THROUGH'}
        target = preselect.pick(context, region, rv3d, mouse)
        if target is None:
            return {'CANCELLED'}
        for ob, cache in cs:
            if ob.as_pointer() == target[0]:
                point, axes = component_frame(ob, cache.bm, target[1], target[2])
                apply_component(context, point, axes, event.shift, event.ctrl)
                if context.mode == 'EDIT_MESH':
                    # Start on the press so native cursor translation receives
                    # the first drag motion. A click simply confirms this placement.
                    bpy.ops.transform.translate('INVOKE_DEFAULT', cursor_transform=True, release_confirm=True)
                return {'FINISHED'}
        return {'CANCELLED'}


classes = (ALLSET_OT_pivot_pick,)
