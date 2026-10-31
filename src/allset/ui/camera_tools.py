# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya panel View menu commands that had no kit counterpart until step 177:

- View > Center View of Selection = Maya ``cmds.viewFit(camera)`` (Maya 2026 panel View menu). In
  Maya the camera keeps its rotation and its straight-line distance to the
  selection's bounding-box centre, and moves so that centre lies on its view axis (persp at (28, 21, 28), a cube at
  (5, 2, -3): rotation unchanged, centre of interest 44.82 -> 43.02 = |centre - eye|).
- View > Camera Attribute Editor... / panel toolbar Camera Attributes = Maya's camera Attribute Editor: the Attribute
  Editor of the camera the panel looks through. Blender's own persp / ortho views have no camera object: a popover
  shows the view's camera values (Focal Length in millimetres, near / far clip) — Maya's perspShape.
- View > Camera Tools > Tumble / Track / Dolly Tool = Maya's camera tools: tools whose LMB drag tumbles / tracks /
  dollies the view (like Alt+LMB / Alt+MMB / Alt+RMB) until another tool is picked (Q / W / E / R).
"""

import bpy
from bpy.props import FloatProperty
from mathutils import Matrix, Vector

TUMBLE_TOOL, TRACK_TOOL, DOLLY_TOOL = "allset.tumble_tool", "allset.track_tool", "allset.dolly_tool"
MAYA_FILM_MM = 36.0       # 35 mm camera film back (create.MAYA_FILM_MM)


# --- Center View of Selection (pure maths) -----------------------------------------------------

def bbox_centre(points):
    pts = [Vector(p) for p in points]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (lo + hi) / 2


def centre_view(eye, forward, centre):
    """Maya viewFit -c: (new eye, distance) of a camera at ``eye`` looking along unit ``forward`` that keeps its
    rotation and its distance to ``centre`` and puts ``centre`` on its view axis."""
    eye, forward, centre = Vector(eye), Vector(forward).normalized(), Vector(centre)
    dist = (centre - eye).length
    return centre - forward * dist, dist


# --- operators ----------------------------------------------------------------------------------

def _view_camera(context):
    from . import panel_menus
    return panel_menus.view_camera(context)


class ALLSET_OT_center_view_selection(bpy.types.Operator):
    """Turn nothing, move the camera so the selection is in the middle of the view at the same distance
    (Maya View > Center View of Selection)"""
    bl_idname = "allset.center_view_selection"
    bl_label = "Center View of Selection"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.region_data is not None

    def execute(self, context):
        from ..operators import view
        space, rv3d = context.space_data, context.region_data
        cam = _view_camera(context)
        pts = view.frame_points(context, space, True, False, exclude=cam)
        if not pts:
            self.report({'WARNING'}, "Nothing to center on")
            return {'CANCELLED'}
        centre = bbox_centre(pts)
        if cam is not None:
            if all(cam.lock_location):            # Maya Lock Camera
                self.report({'WARNING'}, f"{cam.name} is locked")
                return {'CANCELLED'}
            loc, rot, scale = cam.matrix_world.decompose()
            eye, _d = centre_view(loc, rot @ Vector((0.0, 0.0, -1.0)), centre)
            cam.matrix_world = Matrix.LocRotScale(eye, rot, scale)
        else:
            rot = rv3d.view_rotation
            forward = rot @ Vector((0.0, 0.0, -1.0))
            if rv3d.view_perspective == 'ORTHO':      # the distance is the ortho zoom: only the centre moves
                rv3d.view_location = centre
            else:
                eye0 = rv3d.view_location + rot @ Vector((0.0, 0.0, rv3d.view_distance))
                _eye, dist = centre_view(eye0, forward, centre)
                rv3d.view_location, rv3d.view_distance = centre, dist
        context.area.tag_redraw()
        return {'FINISHED'}


def _persp_focal_get(self):
    space = bpy.context.space_data
    if space is None or space.type != 'VIEW_3D':
        return 35.0
    from ..operators.key_batch import VIEW_SENSOR
    return space.lens * MAYA_FILM_MM / VIEW_SENSOR


def _persp_focal_set(self, value):
    space = bpy.context.space_data
    if space is not None and space.type == 'VIEW_3D':
        from ..operators.key_batch import VIEW_SENSOR
        space.lens = value * VIEW_SENSOR / MAYA_FILM_MM


class ALLSET_PT_persp_camera(bpy.types.Panel):
    """The camera values of a Blender persp / ortho view (Maya perspShape)"""
    bl_idname = "ALLSET_PT_persp_camera"
    bl_label = "perspShape"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 13

    def draw(self, context):
        layout = self.layout
        space = context.space_data
        layout.label(text="perspShape (this view's camera)")
        col = layout.column()
        col.use_property_split = True
        col.prop(context.window_manager, "allset_persp_focal")
        if space is not None and space.type == 'VIEW_3D':
            col.prop(space, "clip_start", text="Near Clip Plane")
            col.prop(space, "clip_end", text="Far Clip Plane")
        layout.label(text="A camera view shows its full Attribute Editor", icon='INFO')


class ALLSET_OT_camera_attribute_editor(bpy.types.Operator):
    """Show the camera this view looks through in the Attribute Editor (Maya View > Camera Attribute Editor)"""
    bl_idname = "allset.camera_attribute_editor"
    bl_label = "Camera Attribute Editor"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    def execute(self, context):
        cam = _view_camera(context)
        if cam is None:
            bpy.ops.wm.call_panel(name=ALLSET_PT_persp_camera.bl_idname, keep_open=True)
            return {'FINISHED'}
        try:   # Maya shows the camera without selecting it; the kit AE shows the active object (as object_attributes)
            cam.select_set(True)
            context.view_layer.objects.active = cam
        except RuntimeError:
            self.report({'WARNING'}, f"{cam.name} is not in the view layer")
            return {'CANCELLED'}
        return bpy.ops.allset.dock_show(dock='ATTRIBUTE_EDITOR')


class ALLSET_OT_track(bpy.types.Operator):
    """Track the view (Maya Alt+MMB, Track Tool)"""
    bl_idname = "allset.track"
    bl_label = "Track"

    @classmethod
    def poll(cls, context):
        return context.region_data is not None

    def invoke(self, context, event):
        from ..operators import view
        view.camera_navigation(context)
        bpy.ops.view3d.move('INVOKE_DEFAULT')
        return {'FINISHED'}


# --- tools ----------------------------------------------------------------------------------------

_TOOLS = (
    (TUMBLE_TOOL, "Tumble Tool", "Drag to tumble the view around its centre of interest (Maya Tumble Tool)",
     "ops.transform.rotate", "allset.tumble"),
    (TRACK_TOOL, "Track Tool", "Drag to track the view (Maya Track Tool)", "ops.transform.translate", "allset.track"),
    (DOLLY_TOOL, "Dolly Tool", "Drag left / right to dolly the view in / out (Maya Dolly Tool)",
     "ops.transform.push_pull", "allset.dolly"),
)


def _tool_class(idname, label, description, icon, op, mode):
    return type(f"ALLSET_TL_{idname.split('.')[1]}_{mode.lower()}", (bpy.types.WorkSpaceTool,), {
        "bl_space_type": 'VIEW_3D', "bl_context_mode": mode, "bl_idname": idname, "bl_label": label,
        "bl_description": description, "bl_icon": icon, "bl_widget": None,
        "bl_keymap": ((op, {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),)})


TOOLS = [_tool_class(*t, mode) for mode in ('OBJECT', 'EDIT_MESH') for t in _TOOLS]
classes = (ALLSET_OT_center_view_selection, ALLSET_PT_persp_camera, ALLSET_OT_camera_attribute_editor, ALLSET_OT_track)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.allset_persp_focal = FloatProperty(
        name="Focal Length", description="Focal length of this view in mm (36 mm film back)",
        get=_persp_focal_get, set=_persp_focal_set, min=2.5, max=3500.0, precision=1)
    for i, tool in enumerate(TOOLS):
        bpy.utils.register_tool(tool, after={"builtin.measure"}, separator=(i % len(_TOOLS) == 0))


def unregister():
    for tool in reversed(TOOLS):
        bpy.utils.unregister_tool(tool)
    del bpy.types.WindowManager.allset_persp_focal
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
