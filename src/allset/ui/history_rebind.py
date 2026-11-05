# SPDX-License-Identifier: GPL-3.0-or-later
"""Select replacement components on a detached proposed history input."""

import json

import bmesh
import bpy
from bpy.props import StringProperty

from .. import live_refs
from ..operators import extrude, history_references, model_history
from . import attribute_edit

_session = None


def draw_controls(layout, ob):
    info = model_history.pending(ob)
    if info is not None:
        column = layout.column(align=True)
        broken = next(item for item in info['data']['nodes'] if item['id'] == info['node_id'])
        column.label(text='Selection required by '+broken['name'], icon='ERROR')
        column.operator('allset.history_rebind', text='Rebind Selection').object_name = ob.name


class ALLSET_OT_history_rebind_apply(bpy.types.Operator):
    bl_idname = 'allset.history_rebind_apply'
    bl_label = 'Rebind History Selection'
    bl_options = {'INTERNAL', 'UNDO'}
    object_name: StringProperty(options={'SKIP_SAVE'})
    selection: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        ob = bpy.data.objects.get(self.object_name)
        if ob is None:
            return {'CANCELLED'}
        try:
            model_history.rebind(ob, json.loads(self.selection))
            return {'FINISHED'}
        except (ValueError, RuntimeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}


class ALLSET_OT_history_rebind(bpy.types.Operator):
    """Choose replacement components on the proposed input, then Enter to apply or Esc to cancel"""
    bl_idname = 'allset.history_rebind'
    bl_label = 'Rebind Selection'
    bl_options = {'INTERNAL'}
    object_name: StringProperty(options={'SKIP_SAVE'})

    def invoke(self, context, event):
        global _session
        ob = bpy.data.objects.get(self.object_name) if self.object_name else context.active_object
        if ob is None or model_history.pending(ob) is None or _session is not None:
            return {'CANCELLED'}
        if ob.name not in context.view_layer.objects:
            self.report({'WARNING'}, 'Open a View Layer containing this object to replace its selection')
            return {'CANCELLED'}
        if context.area is None or context.area.type != 'VIEW_3D' or context.region.type != 'WINDOW':
            area = max((a for a in context.window.screen.areas if a.type == 'VIEW_3D'),
                       key=lambda a:a.width*a.height, default=None)
            region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
            if region is None:
                return {'CANCELLED'}
            with context.temp_override(area=area, region=region):
                return bpy.ops.allset.history_rebind('INVOKE_DEFAULT', object_name=ob.name)
        if not attribute_edit.claim(context, self):
            return {'CANCELLED'}
        self._window, self._area = context.window.as_pointer(), context.area.as_pointer()
        self._scene = context.scene
        self._layer = context.view_layer
        self._object = ob.name
        self.properties.property_unset('object_name')
        self._selected = [item.name for item in context.selected_objects]
        self._active = context.active_object.name if context.active_object else None
        self._mode = context.mode
        self._select_mode = tuple(context.scene.tool_settings.mesh_select_mode)
        self._hidden = ob.hide_get()
        self._preview = None
        self._mesh_name = None
        self._handler = self._ghost_handler = None
        self._finished = False
        self._ghost = []
        try:
            candidate, node = model_history.binding_input(ob)
            try:
                self._node_name = node['name']
                mesh = bpy.data.meshes.new('.allset_rebind_input')
                self._mesh_name = mesh.name
                candidate.to_mesh(mesh)
            finally:
                candidate.free()
            try:
                old = model_history.input_mesh(ob, node['id'])
                try:
                    for edge in old.edges:
                        if edge.select:
                            self._ghost.extend(tuple(ob.matrix_world @ vertex.co) for vertex in edge.verts)
                            if len(self._ghost) >= 8192:
                                break
                finally:
                    old.free()
            except (ValueError, RuntimeError):
                pass
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            ob.hide_set(True)
            bpy.ops.object.select_all(action='DESELECT')
            for material in ob.data.materials:
                mesh.materials.append(material)
            preview = bpy.data.objects.new('Rebind '+node['name'], mesh)
            context.scene.collection.objects.link(preview)
            preview.matrix_world = ob.matrix_world.copy()
            preview['allset_history_rebind_preview'] = True
            self._preview = preview.name
            preview.select_set(True)
            context.view_layer.objects.active = preview
            mode = node['selection']['mode']
            context.scene.tool_settings.mesh_select_mode = tuple(value in mode for value in ('VERT','EDGE','FACE'))
            bpy.ops.object.mode_set(mode='EDIT')
            self._input_hash = extrude.coords_hash(bmesh.from_edit_mesh(mesh))
            self._handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_overlay, (), 'WINDOW', 'POST_PIXEL')
            self._ghost_handler = bpy.types.SpaceView3D.draw_handler_add(self.draw_ghost, (), 'WINDOW', 'POST_VIEW')
            _session = self
            context.window_manager.modal_handler_add(self)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        except (ValueError, RuntimeError, ReferenceError) as error:
            self.report({'WARNING'}, str(error))
            self.close(context, cancel=True)
            return {'CANCELLED'}

    def close(self, context, cancel=False):
        global _session
        if self._finished:
            return
        if (self._scene in bpy.data.scenes.values() and self._layer in self._scene.view_layers.values()
                and (context.scene != self._scene or context.view_layer != self._layer)):
            with context.temp_override(scene=self._scene, view_layer=self._layer):
                self.close(context, cancel)
            return
        self._finished = True
        for handle in (self._handler, self._ghost_handler):
            if handle is not None:
                bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
        preview = bpy.data.objects.get(self._preview) if self._preview else None
        if preview is not None:
            if preview.mode == 'EDIT':
                context.view_layer.objects.active = preview
                bpy.ops.object.mode_set(mode='OBJECT')
            mesh = preview.data
            bpy.data.objects.remove(preview, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        elif self._mesh_name:
            mesh = bpy.data.meshes.get(self._mesh_name)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        ob = bpy.data.objects.get(self._object)
        if ob is not None:
            ob.hide_set(self._hidden)
            if cancel:
                model_history._pending.pop(ob.data.session_uid, None)
        if context.mode == 'OBJECT':
            bpy.ops.object.select_all(action='DESELECT')
            for name in self._selected:
                item = bpy.data.objects.get(name)
                if item is not None:
                    item.select_set(True)
            active = bpy.data.objects.get(self._active) if self._active else None
            context.view_layer.objects.active = active
            context.scene.tool_settings.mesh_select_mode = self._select_mode
            if self._mode == 'EDIT_MESH' and active is not None and context.window.view_layer == self._layer:
                bpy.ops.object.mode_set(mode='EDIT')
        attribute_edit.release(self._window, self)
        _session = None
        if context.area:
            context.area.tag_redraw()

    def cancel(self, context):
        self.close(context, cancel=True)

    def modal(self, context, event):
        if self._finished:
            return {'CANCELLED'}
        preview = bpy.data.objects.get(self._preview)
        ob = bpy.data.objects.get(self._object)
        if (context.scene != self._scene or preview is None or context.active_object != preview
                or context.view_layer != self._layer or context.mode != 'EDIT_MESH'
                or ob is None or model_history.pending(ob) is None):
            self.close(context, cancel=True)
            return {'CANCELLED'}
        if event.type == 'ESC' and event.value == 'PRESS':
            self.close(context, cancel=True)
            return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            bm = bmesh.from_edit_mesh(preview.data)
            if extrude.coords_hash(bm) != self._input_hash:
                self.report({'WARNING'}, 'The proposed input was edited. Cancel and select replacement components again.')
                return {'RUNNING_MODAL'}
            if not any(v.select for v in bm.verts):
                self.report({'WARNING'}, 'Select replacement components first')
                return {'RUNNING_MODAL'}
            selection = history_references.pack(model_history._selection(bm))
            name = ob.name
            self.close(context)
            result = bpy.ops.allset.history_rebind_apply('EXEC_DEFAULT', True,
                                                        object_name=name, selection=json.dumps(selection))
            if model_history.pending(ob) is not None:
                bpy.ops.allset.history_rebind('INVOKE_DEFAULT', object_name=name)
            return result
        return {'PASS_THROUGH'}

    def draw_overlay(self):
        context = bpy.context
        if context.area.as_pointer() == self._area and context.window.as_pointer() == self._window:
            from .in_view import _text
            _text(20, context.region.height-36, self._node_name+' — choose replacement components', (1,.8,.2,1), 14)
            _text(20, context.region.height-56, 'Enter apply   Esc cancel   Red outlines show the previous target', (1,1,1,1), 12)

    def draw_ghost(self):
        if not self._ghost or bpy.context.area.as_pointer() != self._area:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float('color', (1,.12,.08,1))
        batch_for_shader(shader, 'LINES', {'pos':self._ghost}).draw(shader)


@bpy.app.handlers.persistent
def clear(_dummy=None):
    if _session is not None:
        window, area = live_refs.find_area(_session._area, _session._window)
        if window is not None and area is not None:
            region = next(region for region in area.regions if region.type == 'WINDOW')
            with bpy.context.temp_override(window=window, area=area, region=region):
                _session.close(bpy.context, cancel=True)


classes = (ALLSET_OT_history_rebind_apply, ALLSET_OT_history_rebind)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.save_pre, bpy.app.handlers.undo_pre,
                     bpy.app.handlers.redo_pre):
        handlers.append(clear)


def unregister():
    clear()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.save_pre, bpy.app.handlers.undo_pre,
                     bpy.app.handlers.redo_pre):
        if clear in handlers:
            handlers.remove(clear)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
