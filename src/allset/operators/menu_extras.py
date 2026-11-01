# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators behind Maya menu items that had no Blender action.

- ``allset.open_editor``: Windows > ... Editors open a floating editor window, like
  Maya's panels torn off into windows.
- ``allset.increment_save``: File > Increment and Save (Maya
  numbering, re-implemented in ``increment_path``).
- ``ALLSET_MT_export_selection``: File > Export Selection... = the exporters with
  "selected only" set.
- ``allset.uv_planar``: UV > Planar / Normal-Based = project the selected faces on the
  plane of their average normal.
"""

import os
import re

import bmesh
import bpy
from bpy.props import EnumProperty, StringProperty
from mathutils import Vector

from .. import results
from .. import live_refs

# --- editor windows ----------------------------------------------------------------------------

EDITOR_TYPES = (
    ('OUTLINER', "Outliner", ""), ('FCURVES', "Graph Editor", ""), ('DOPESHEET', "Dope Sheet", ""),
    ('NLA_EDITOR', "Nonlinear Animation", ""), ('DRIVERS', "Drivers", ""),
    ('SEQUENCE_EDITOR', "Video Sequencer", ""), ('ShaderNodeTree', "Shader Editor", ""),
    ('UV', "UV Editor", ""), ('SPREADSHEET', "Spreadsheet", ""), ('TEXT_EDITOR', "Text Editor", ""),
    ('PROPERTIES', "Properties", ""),
    # Windows > Command Shell / Content Browser, File > View Image
    ('CONSOLE', "Python Console", ""), ('ASSETS', "Asset Browser", ""), ('IMAGE_EDITOR', "Image Editor", ""),
    # Windows > Bifrost Graph Editor (menu_map) opens Geometry Nodes; it was missing here and raised
    ('GeometryNodeTree', "Geometry Node Editor", ""),
)


def _maya_outliner(space):
    # Same filters as the Maya Workflow Kit layout's Outliner (Maya DAG).
    from ..ui import maya_outliner
    maya_outliner.setup(space)


def open_window(context, area, kind=None):
    """Duplicate ``area`` into a new window (Maya's floating editor windows); the new window or None. ``kind`` =
    the window's name: it opens at the size and place it had when it was last closed (ui/window_places.py,
    #203)."""
    from ..ui import window_places
    return window_places.open_at(context, area, kind)


# Timers below keep the window's pointer and look it up each tick (live_refs, #36).
def sidebar_tab_later(window, category, tries=100):
    """Show the sidebar of ``window``'s only area and make ``category`` its active tab.

    ``Region.active_panel_category`` can be set once the region has drawn its tabs (before that it raises
    "read-only";
    a new window's sidebar starts on the first tab, Node / Item, whatever ``bl_order`` says), and
    ``show_region_ui`` set inside an operator doesn't stick: both run from a timer."""
    state = {"n": tries}

    ptr = window.as_pointer()

    def tick():
        window = live_refs.window(ptr)
        if window is None:
            return None
        try:
            area = window.screen.areas[0]
            space = area.spaces.active
            if not space.show_region_ui:
                space.show_region_ui = True
            region = next(r for r in area.regions if r.type == 'UI')
            if region.width > 1:
                try:
                    region.active_panel_category = category
                except (TypeError, AttributeError):
                    # "read-only" until the region has drawn its tabs (a copied region at first): next tick
                    pass
                if region.active_panel_category == category:
                    area.tag_redraw()
                    return None
            area.tag_redraw()
        except (ReferenceError, StopIteration, AttributeError, IndexError):   # window closed meanwhile
            return None
        state["n"] -= 1
        return 0.05 if state["n"] > 0 else None

    bpy.app.timers.register(tick, first_interval=0.01)


def properties_tab_later(window, tab, tries=40):
    """Put the new window's Properties editor on ``tab``: a Properties space made in this operator has no tab
    list until it has drawn, so the assignment is retried from a timer (it stays OBJECT otherwise)."""
    state = {"n": tries}

    ptr = window.as_pointer()

    def tick():
        window = live_refs.window(ptr)
        if window is None:
            return None
        # Reading ``space.context`` before the tab list exists prints an rna enum WARN, so only a
        # successful assignment is read back.
        try:
            space = window.screen.areas[0].spaces.active
            try:
                space.context = tab
            except TypeError:   # tab not available yet (or ever: no active object etc.)
                pass
            else:
                if space.context == tab:
                    window.screen.areas[0].tag_redraw()
                    return None
        except (ReferenceError, AttributeError, IndexError):   # window closed meanwhile
            return None
        state["n"] -= 1
        return 0.05 if state["n"] > 0 else None

    if tick() is not None:
        bpy.app.timers.register(tick, first_interval=0.05)


class ALLSET_OT_open_editor(bpy.types.Operator):
    """Open this editor in a new window (Maya Windows menu)"""
    bl_idname = "allset.open_editor"
    bl_label = "Open Editor"

    ui_type: EnumProperty(items=EDITOR_TYPES, name="Editor")
    tab: StringProperty(name="Properties Tab", options={'SKIP_SAVE'})
    display_mode: StringProperty(name="Outliner Display Mode", options={'SKIP_SAVE'},
                                 description="e.g. LIBRARIES = Blender File (Maya Reference Editor)")

    def execute(self, context):
        window = context.window
        if window is None:
            return {'CANCELLED'}
        if self.ui_type == 'UV':
            # Maya UV > UV Editor shows the object's UVs at once: edit mode + UV Sync Selection, one editor
            from . import uv_tools
            from ..ui import window_places
            if not window_places.reopening(f"editor:{self.ui_type}"):
                # the second run (window at its remembered place) must not undo what the first run's caller
                # set meanwhile, e.g. F12's UV mode (UV Sync Selection off)
                uv_tools.prepare(context)
            if uv_tools.find_uv_editor(context)[1] is not None:
                return {'FINISHED'}
        area = max(window.screen.areas, key=lambda a: a.width * a.height, default=None)
        if area is None:
            return {'CANCELLED'}
        new = open_window(context, area, f"editor:{self.ui_type}")
        if new is None:
            from ..ui import window_places
            if not window_places.deferred():     # opens on a later tick (#203)
                self.report({'ERROR'}, "Could not open a new window")
            return {'CANCELLED'}
        target = new.screen.areas[0]
        target.ui_type = self.ui_type
        if self.ui_type == 'OUTLINER':
            if self.display_mode:
                target.spaces.active.display_mode = self.display_mode
            else:
                _maya_outliner(target.spaces.active)
        if self.ui_type == 'PROPERTIES' and self.tab:
            properties_tab_later(new, self.tab)
        if self.ui_type in {'FCURVES', 'DOPESHEET', 'UV'}:
            from ..ui import editor_chrome   # Maya editor chrome: framing, folded rows, UV Toolkit
            editor_chrome.prepare_later(new, self.ui_type)
        return {'FINISHED'}


# --- Increment and Save --------------------------------------------------------------------------

_VERSION = re.compile(r"^(.*)\.(\d+)$")


def increment_path(path):
    """Next file of Maya's Increment and Save: the digits after the last '.' of the root name
    go up by one with their width kept, else '.0001' is appended (MyFile.blend ->
    MyFile.0001.blend, MyFile.0043 -> 0044, MyFile.99 -> MyFile.100, MyFile01 -> MyFile01.0001;
    Maya's Increment and Save, behaviour only)."""
    folder, name = os.path.split(path)
    root, ext = os.path.splitext(name)
    m = _VERSION.match(root)
    if m:
        number = str(int(m.group(2)) + 1).zfill(len(m.group(2)))
        root = f"{m.group(1)}.{number}"
    else:
        root = f"{root}.0001"
    return os.path.join(folder, root + ext)


class ALLSET_OT_increment_save(bpy.types.Operator):
    """Save under the next version number and keep working in it (Maya Increment and Save)"""
    bl_idname = "allset.increment_save"
    bl_label = "Increment and Save"

    def invoke(self, context, event):
        if not bpy.data.filepath:
            # Never saved: Maya opens Save As.
            return bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT')
        return self.execute(context)

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'WARNING'}, "Save the scene once first")
            return {'CANCELLED'}
        new = increment_path(bpy.data.filepath)
        # Maya asks before replacing an existing file; never overwrite, take the next free
        # number instead (a kit choice).
        while os.path.exists(new):
            new = increment_path(new)
        bpy.ops.wm.save_as_mainfile(filepath=new, copy=False)
        results.result(self, f"Saved {os.path.basename(new)}")
        return {'FINISHED'}


# --- Export Selection ------------------------------------------------------------------------------

# (operator, "selected only" property, label); each opens its file browser.
EXPORTERS = (
    ("export_scene.fbx", "use_selection", "FBX (.fbx)"),
    ("wm.obj_export", "export_selected_objects", "OBJ (.obj)"),
    ("export_scene.gltf", "use_selection", "glTF 2.0 (.glb/.gltf)"),
    ("wm.usd_export", "selected_objects_only", "USD (.usd*)"),
    ("wm.alembic_export", "selected", "Alembic (.abc)"),
)


def available_exporters():
    out = []
    for idname, prop, label in EXPORTERS:
        mod, name = idname.split(".")
        try:
            getattr(getattr(bpy.ops, mod), name).get_rna_type()
        except (AttributeError, KeyError):
            continue
        out.append((idname, prop, label))
    return out


class ALLSET_MT_export_selection(bpy.types.Menu):
    """Export only the selected objects (Maya File > Export Selection)"""
    bl_idname = "ALLSET_MT_export_selection"
    bl_label = "Export Selection"

    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'
        for idname, prop, label in available_exporters():
            op = layout.operator(idname, text=label)
            setattr(op, prop, True)


# --- UV planar --------------------------------------------------------------------------------------

def planar_uvs(points, normal):
    """UVs of ``points`` projected on the plane of ``normal``, fitted in 0-1 keeping the
    aspect ratio (Maya's planar projection with "keep image width/height ratio")."""
    n = Vector(normal).normalized() if Vector(normal).length > 1e-9 else Vector((0, 0, 1))
    # u = the world axis most perpendicular to the normal, flattened onto the plane, so a
    # face looking along Z gets U = X and V = Y (not a diagonal).
    axis = min((Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))), key=lambda a: abs(a.dot(n)))
    u = (axis - n * axis.dot(n)).normalized()
    v = n.cross(u).normalized()
    flat = [(p.dot(u), p.dot(v)) for p in points]
    if not flat:
        return []
    x0, y0 = min(f[0] for f in flat), min(f[1] for f in flat)
    size = max(max(f[0] for f in flat) - x0, max(f[1] for f in flat) - y0) or 1.0
    return [((x - x0) / size, (y - y0) / size) for x, y in flat]


class ALLSET_OT_uv_planar(bpy.types.Operator):
    """Project UVs on the plane of the faces' average normal (Maya Planar / Normal-Based)"""
    bl_idname = "allset.uv_planar"
    bl_label = "Planar Projection"
    bl_options = {'REGISTER', 'UNDO'}

    # Maya's Planar Map X / Y / Z (Shift+RMB Mapping submenu) project along a fixed Maya axis (Y up -> Blender Z)
    axis: EnumProperty(items=(('NORMAL', "Faces", "Plane of the faces' average normal"), ('X', "X", ""),
                              ('Y', "Y", ""), ('Z', "Z", "")), name="Project Along", options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH' and context.mode in {'EDIT_MESH', 'OBJECT'}

    def execute(self, context):
        fixed = {'X': Vector((1, 0, 0)), 'Y': Vector((0, 0, 1)), 'Z': Vector((0, -1, 0))}.get(self.axis)
        obs = [o for o in (context.objects_in_mode if context.mode == 'EDIT_MESH' else context.selected_objects)
               if o.type == 'MESH']
        for ob in obs:
            edit = ob.mode == 'EDIT'
            bm = bmesh.from_edit_mesh(ob.data) if edit else bmesh.new()
            if not edit:
                bm.from_mesh(ob.data)
            faces = [f for f in bm.faces if f.select] if edit else list(bm.faces)
            if not faces:
                if not edit:
                    bm.free()
                continue
            layer = bm.loops.layers.uv.active or bm.loops.layers.uv.new("UVMap")
            normal = fixed if fixed is not None else sum((f.normal * f.calc_area() for f in faces), Vector())
            loops = [lp for f in faces for lp in f.loops]
            for lp, uv in zip(loops, planar_uvs([lp.vert.co for lp in loops], normal)):
                lp[layer].uv = uv
            if edit:
                bmesh.update_edit_mesh(ob.data)
            else:
                bm.to_mesh(ob.data)
                bm.free()
        return {'FINISHED'}


classes = (ALLSET_OT_open_editor, ALLSET_OT_increment_save, ALLSET_MT_export_selection,
           ALLSET_OT_uv_planar)
