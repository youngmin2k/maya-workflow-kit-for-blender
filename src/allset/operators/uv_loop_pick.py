# SPDX-License-Identifier: GPL-3.0-or-later
"""Double-click selection in the UV Editor, following the kit's 3D View double-click (operators/loop_pick.py).

- Double-click a UV edge = its UV edge loop; Ctrl+double-click = its UV edge ring.
- Double-click a UV or a UV face = its UV shell.
- Shift adds the loop / ring / shell to the selection (plain replaces it).

It works with UV Sync Selection off (UVs, UV edges and UV faces picked apart from the mesh) and on (mesh vertices,
edges and faces). While whole shells are picked (UV Shell mask or island selection) a click already takes the shell,
so the double-click passes through.

Blender's own UV picks do the walking (``uv.select_loop``, ``uv.select_edge_ring``, ``uv.select_linked_pick``): they
follow UV edges, so a loop stops at a UV seam like a mesh loop stops at a border. "Shift = add" is done here: the
selection from before is put back on top of the replaced one, so Shift never takes a loop away again.
"""

import bmesh
import bpy
from bpy.props import BoolProperty, FloatVectorProperty

from .. import compat, undo_steps


def pick_kind(component, ring):
    """What a double-click on ``component`` ('VERTEX' / 'EDGE' / 'FACE') selects: 'LOOP', 'RING' or 'SHELL'."""
    if ring:
        return 'RING'
    return 'LOOP' if component == 'EDGE' else 'SHELL'


def _meshes(context):
    return [o for o in (getattr(context, "objects_in_mode_unique_data", None) or ()) if o and o.type == 'MESH']


def snapshot(bm, synced):
    """The selection a Shift+double-click keeps: mesh elements with UV Sync on, else the per-corner UV flags."""
    if synced:
        return ("MESH", [v.index for v in bm.verts if v.select], [e.index for e in bm.edges if e.select],
                [f.index for f in bm.faces if f.select])
    corners = [(f.index, [(lp.uv_select_vert, lp.uv_select_edge) for lp in f.loops], f.uv_select) for f in bm.faces]
    return ("UV", corners)


def restore_on_top(bm, snap):
    """Select again what ``snap`` held, keeping whatever is selected now."""
    if snap[0] == "MESH":
        for seq, chosen in zip((bm.verts, bm.edges, bm.faces), snap[1:]):
            seq.ensure_lookup_table()
            for i in chosen:
                seq[i].select = True
        bm.select_flush_mode()
        compat.uv_sync_from_mesh(bm)
        return
    bm.faces.ensure_lookup_table()
    for fi, flags, face_sel in snap[1]:
        face = bm.faces[fi]
        for lp, (vert, edge) in zip(face.loops, flags):
            if vert:
                lp.uv_select_vert = True
            if edge:
                lp.uv_select_edge = True
        if face_sel:
            face.uv_select = True


@undo_steps.no_redo_panel      # no Adjust Last Operation (Maya has none)
class ALLSET_OT_uv_loop_pick(bpy.types.Operator):
    """UV Editor double-click: a UV edge selects its UV edge loop (Ctrl: its edge ring), a UV or a UV face its
    UV shell; Shift adds to the selection"""
    bl_idname = "allset.uv_loop_pick"
    bl_label = "Select UV Loop (Double-Click)"
    bl_options = {'REGISTER', 'UNDO'}

    ring: BoolProperty(name="Ring", options={'SKIP_SAVE'}, description="Select the UV edge ring instead of the loop")
    extend: BoolProperty(name="Add", options={'SKIP_SAVE'}, description="Add to the selection")
    location: FloatVectorProperty(name="Location", size=2, options={'SKIP_SAVE', 'HIDDEN'},
                                  description="Picked point in UV space")

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def _component(self, context):
        from ..ui import uv_shell_preview
        if uv_shell_preview.shell_mode(context):
            return None
        return uv_shell_preview.component_mode(context) or 'VERTEX'

    def execute(self, context):
        component = self._component(context)
        if component is None:
            return {'CANCELLED'}
        synced = context.scene.tool_settings.use_uv_select_sync
        kept = []
        if self.extend:
            kept = [(ob, snapshot(bmesh.from_edit_mesh(ob.data), synced)) for ob in _meshes(context)]
        kind = pick_kind(component, self.ring)
        loc = tuple(self.location)
        try:
            if kind == 'LOOP':
                result = bpy.ops.uv.select_loop(location=loc, extend=False)
            elif kind == 'RING':
                result = bpy.ops.uv.select_edge_ring(location=loc, extend=False)
            else:
                result = bpy.ops.uv.select_linked_pick(location=loc, extend=False, deselect=False)
        except RuntimeError:
            return {'CANCELLED'}
        if 'FINISHED' not in result:
            return {'CANCELLED'}
        for ob, snap in kept:
            bm = bmesh.from_edit_mesh(ob.data)
            restore_on_top(bm, snap)
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        return {'FINISHED'}

    def invoke(self, context, event):
        region = context.region
        if (context.area is None or context.area.type != 'IMAGE_EDITOR' or region is None
                or region.type != 'WINDOW' or self._component(context) is None):
            return {'PASS_THROUGH'}       # whole shells: the click (sent again as a press) picks the shell
        self.location = region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        result = self.execute(context)
        return result if 'FINISHED' in result else {'PASS_THROUGH'}


classes = (ALLSET_OT_uv_loop_pick,)
