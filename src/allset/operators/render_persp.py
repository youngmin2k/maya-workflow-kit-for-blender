# SPDX-License-Identifier: GPL-3.0-or-later
"""Render > Render Current Frame / Render Sequence in a scene without a render camera.

Maya renders the active panel's camera; a new Maya scene renders through ``persp``. Blender renders through
``scene.camera`` only and stops with "No camera found" without one (the Maya layout's views aren't cameras). The
kit's render items therefore run ``allset.render``:

- a scene camera the user set is used as it is: Blender's own render;
- otherwise the render goes through the camera the view looks through (camera view: its local camera, else the
  scene camera), else through ``persp``: Maya's startup persp camera of a kit new scene
  (``operators/startup_cameras.py``), or a kit ``persp`` camera made on the first render (object ``persp`` / data ``perspShape``, ID property ``allset_persp``,
  in no collection and kept by a fake user, so it isn't a second Outliner row, isn't exported and doesn't render
  as an object). It is placed where the view looks from with the view's lens (Blender's viewport lens is on a
  72 mm sensor) and Maya clip planes, made ``scene.camera``, and placed again at every render while it is still
  the scene camera.

The view is the 3D View the operator runs in, else the main window's largest 3D View (not the Tool Box column).
"""

import bpy
from bpy.props import BoolProperty

from .. import results
from . import framing, units
from .key_batch import VIEW_SENSOR, camera_matrix

PROP = "allset_persp"
NAME, SHAPE = "persp", "perspShape"
MAYA_FILM_MM = 36.0          # film back of the 35 mm camera (create.MAYA_FILM_MM)
STARTUP = "allset_startup_camera"


def persp_camera(create=True):
    """The camera persp renders through: the scene's startup persp, else the kit's (made when ``create``)."""
    scene = bpy.context.scene
    ob = next((o for o in scene.objects if o.type == 'CAMERA' and o.get(STARTUP) == NAME),
              None) if scene is not None else None
    ob = ob or next((o for o in bpy.data.objects if o.get(PROP) and o.type == 'CAMERA'), None)
    if ob is None and create:
        data = bpy.data.cameras.new(SHAPE)
        data.sensor_width = MAYA_FILM_MM
        ob = bpy.data.objects.new(NAME, data)
        ob[PROP] = True
        ob.use_fake_user = True
    return ob


def is_persp(ob):
    """True for a camera the kit places from the view (the kit persp, a startup persp)."""
    return ob is not None and (bool(ob.get(PROP)) or ob.get(STARTUP) == NAME)


def match_view(ob, space, rv3d, scene=None):
    """Put camera ``ob`` where the view (``space``, ``rv3d``) looks from, with the same lens."""
    cam = ob.data
    # from view_location / rotation / distance: rv3d.view_matrix is only recomputed when the view draws
    ob.matrix_world = camera_matrix(framing.view_matrix(rv3d.view_location, rv3d.view_rotation, rv3d.view_distance))
    if rv3d.view_perspective != 'ORTHO':
        cam.type = 'PERSP'
        cam.lens = space.lens * cam.sensor_width / VIEW_SENSOR
    else:
        cam.type = 'ORTHO'
        cam.ortho_scale = rv3d.view_distance * VIEW_SENSOR / space.lens
    clip = units.clip(scene)
    cam.clip_start, cam.clip_end = clip["clip_start"], clip["clip_end"]


def _is_toolbox(space):
    from ..ui import toolbox
    return toolbox.is_toolbox(space)


def find_view(context):
    """(space, region_3d) of the view the render follows, or (None, None)."""
    area = context.area
    if area is not None and area.type == 'VIEW_3D' and not _is_toolbox(area.spaces.active):
        space = area.spaces.active
        return space, space.region_3d
    from ..ui import maya_dock, status_line
    wm = context.window_manager
    windows = [maya_dock.main_window(wm)] if wm.windows else []
    windows += [w for w in wm.windows if w not in windows]
    for window in windows:
        if window is None:
            continue
        area, _region = status_line.main_view3d(window.screen)
        if area is not None and not _is_toolbox(area.spaces.active):
            space = area.spaces.active
            return space, space.region_3d
    return None, None


def needs_camera(scene):
    """True when the render picks its camera itself: no scene camera, or one the kit places from the view."""
    return scene.camera is None or is_persp(scene.camera)


def render_camera(context):
    """Make the camera the render goes through ``scene.camera`` (see the module text); returns it."""
    scene = context.scene
    space, rv3d = find_view(context)
    ob = None
    if space is not None and rv3d is not None and rv3d.view_perspective == 'CAMERA':
        # camera view: the camera it looks through stays where it is
        ob = space.camera if space.use_local_camera and space.camera is not None else scene.camera
    if ob is None:
        ob = persp_camera()
        if rv3d is not None:        # no 3D View at all (background): persp stays where it was
            match_view(ob, space, rv3d, scene)
    scene.camera = ob
    return ob


class ALLSET_OT_render(bpy.types.Operator):
    """Render with Blender's render; a scene without a camera renders through persp, placed where the view looks
    from (like Maya)"""
    bl_idname = "allset.render"
    bl_label = "Render"
    bl_options = {'REGISTER'}

    animation: BoolProperty(name="Animation", default=False, options={'SKIP_SAVE', 'HIDDEN'})
    write_still: BoolProperty(name="Write Image", default=False, options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def _render(self, context, how):
        scene = context.scene
        ob = render_camera(context) if needs_camera(scene) else scene.camera
        props = {"animation": self.animation}
        if self.write_still and not self.animation:
            props["write_still"] = True
        try:
            res = bpy.ops.render.render(how, **props)
        except RuntimeError as ex:
            self.report({'ERROR'}, str(ex))
            return {'CANCELLED'}
        if 'CANCELLED' in res:
            return {'CANCELLED'}
        results.result(self, f"Rendering through {ob.name}")
        return {'FINISHED'}

    def invoke(self, context, event):
        if context.window is None or bpy.app.background:
            return self.execute(context)
        return self._render(context, 'INVOKE_DEFAULT')

    def execute(self, context):
        return self._render(context, 'EXEC_DEFAULT')


classes = (ALLSET_OT_render,)
