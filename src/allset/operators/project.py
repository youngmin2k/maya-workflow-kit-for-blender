# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya projects, scene saving and references.

Blender has no project system. A Maya Workflow Kit project is a root folder with Maya's standard sub-folders
(Project Window) and a marker file; the current project and Recent Projects live in
the add-on preferences (like Maya keeps the workspace in its prefs). Effects:

- File > Open / Save As (Ctrl+O / Ctrl+S on a new file / Ctrl+Shift+S) and Create Reference start in
  ``<root>/scenes`` (``wm.open_mainfile`` / ``wm.save_as_mainfile`` invoked with that ``filepath``);
- a file saved inside the project renders to ``<root>/images`` (relative ``//../images/``) when its render
  output is still Blender's default (``save_pre`` gets the path being saved);
- opening a ``.blend`` under ``<root>/scenes`` of a marked project makes it the current project.

Create Reference (Ctrl+R) = link the other file's scene contents and make them editable with a library override
(Maya reference edits), under a ``<namespace>`` collection with ``ns:`` name prefixes (Blender has no namespaces).
"""

import json
import os

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, StringProperty

from .. import results
from ..names import PRODUCT

# Maya's standard project folders (Scenes, Templates = assets, Images, Source Images, Render Data,
# Clips, Sound, Scripts, Disk Cache = data, Movies, ..., AutoSave); "cache" for Blender's simulation caches.
FOLDERS = ("scenes", "assets", "images", "sourceimages", "renderData", "clips", "sound", "scripts", "data", "movies",
           "cache", "autosave")
MARKER = "allset_project.json"
RECENT_MAX = 10
DIALOG_WIDTH = 420
# Blender's factory render output ('/tmp\\' on Windows).
DEFAULT_RENDER_PATHS = {"", "/tmp\\", "/tmp/", "//"}
NOTICE = ("Blender has no project system: Maya Workflow Kit keeps this folder as your project. File dialogs open in its "
          "scenes folder, renders go to its images folder and paths are saved relative (//).")


def _prefs(context=None):
    from .. import preferences
    try:
        return preferences.get(context)
    except KeyError:
        return None


def _norm(path):
    return os.path.normcase(os.path.abspath(bpy.path.abspath(path))) if path else ""


# Like Maya, which keeps a default project under <Documents>/maya/projects, a dialog never starts in a
# bare Documents folder. The kit's own default sits next to it
# under "Maya Workflow Kit/" (the product name; the user's real Maya folder is never written);
# ALLSET_PROJECTS_DIR moves it (test sandboxes).
DEFAULT_NAME = "default"


def projects_dir():
    return os.environ.get("ALLSET_PROJECTS_DIR") or \
        os.path.join(os.path.expanduser("~"), "Documents", PRODUCT, "projects")


def default_root():
    return os.path.join(projects_dir(), DEFAULT_NAME)


def current_root(context=None):
    """The current project: the one set (Set Project / Project Window / opened scene), else the default project."""
    prefs = _prefs(context)
    root = prefs.project_root if prefs is not None else ""
    return os.path.abspath(bpy.path.abspath(root)) if root else default_root()


def ensure_root(context=None):
    """The current project root; the default project's folders are made on first use (like Maya's first start)."""
    root = current_root(context)
    if _norm(root) == _norm(default_root()) and not is_project(root):
        try:
            create_project(root)
        except OSError:
            pass
    return root


def recent(context=None):
    prefs = _prefs(context)
    return [p for p in (prefs.recent_projects.split("\n") if prefs else []) if p]


def set_current(root, context=None):
    """Make ``root`` the current project and put it first in Recent Projects."""
    prefs = _prefs(context)
    if prefs is None:
        return
    root = os.path.abspath(root)
    prefs.project_root = root
    items = [root] + [p for p in recent(context) if _norm(p) != _norm(root)]
    prefs.recent_projects = "\n".join(items[:RECENT_MAX])


def create_project(root, folders=FOLDERS):
    """Make the project folders and the marker file; returns the folders made."""
    made = []
    for name in folders:
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
            made.append(name)
    with open(os.path.join(root, MARKER), "w", encoding="utf-8") as fh:
        json.dump({"folders": list(folders)}, fh, indent=1)
    return made


def is_project(root):
    return bool(root) and os.path.isfile(os.path.join(root, MARKER))


def inside(path, root):
    if not path or not root:
        return False
    path, root = _norm(path), _norm(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def detect_root(blend_path):
    """The marked project whose ``scenes`` folder holds ``blend_path`` (any depth), or ""."""
    folder = os.path.dirname(os.path.abspath(blend_path)) if blend_path else ""
    while folder and os.path.dirname(folder) != folder:
        if os.path.basename(folder).lower() == "scenes" and is_project(os.path.dirname(folder)):
            return os.path.dirname(folder)
        folder = os.path.dirname(folder)
    return ""


def scenes_dir(context=None):
    root = ensure_root(context)
    return os.path.join(root, "scenes") if root else ""


def open_path(context=None):
    """Where File > Open starts: the project's scenes folder ("" = Blender's own choice)."""
    folder = scenes_dir(context)
    return os.path.join(folder, "") if folder and os.path.isdir(folder) else ""


def save_as_path(context=None):
    """Where Save As starts: a file already in the project keeps its folder, else the project's scenes folder."""
    folder = scenes_dir(context)
    current = bpy.data.filepath
    if not folder or not os.path.isdir(folder):
        return ""
    if current and inside(current, current_root(context)):
        return current
    return os.path.join(folder, os.path.basename(current) if current else "untitled.blend")


def images_relpath(blend_path, root):
    rel = os.path.relpath(os.path.join(root, "images"), os.path.dirname(os.path.abspath(blend_path)))
    return "//" + rel.replace("\\", "/").rstrip("/") + "/"


def fix_render_output(blend_path, root):
    """Point Blender-default render outputs of every scene at the project's images folder; scenes changed."""
    changed = []
    for scene in bpy.data.scenes:
        if scene.library is None and scene.render.filepath in DEFAULT_RENDER_PATHS:
            scene.render.filepath = images_relpath(blend_path, root)
            changed.append(scene.name)
    return changed


@persistent
def _on_save_pre(filepath, *_args):
    if not isinstance(filepath, str) or not filepath:
        return
    from . import autosave
    if autosave.saving():       # an autosave copy leaves the open scene as it is
        return
    root = current_root() or detect_root(filepath)
    if root and inside(filepath, root):
        fix_render_output(filepath, root)


@persistent
def _on_load_post(filepath, *_args):
    path = filepath if isinstance(filepath, str) else bpy.data.filepath
    root = detect_root(path)
    if root and _norm(root) != _norm(current_root()):
        set_current(root)


# --- operators: project ---------------------------------------------------------------------------

class ALLSET_OT_set_project(bpy.types.Operator):
    """Choose the project folder: file dialogs open in its scenes folder, renders go to its images folder
    (Maya File > Set Project; Blender has no projects)"""
    bl_idname = "allset.set_project"
    bl_label = "Set Project"

    directory: StringProperty(subtype='DIR_PATH')
    filter_folder: BoolProperty(default=True, options={'HIDDEN'})
    create_folders: BoolProperty(name="Create Default Folders", default=True,
                                 description="Make Maya's project folders (scenes, sourceimages, images ...) "
                                             "that are missing (Maya: Create Default Workspace)")

    def invoke(self, context, event):
        self.directory = ensure_root(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        root = os.path.abspath(bpy.path.abspath(self.directory))
        if not os.path.isdir(root):
            self.report({'ERROR'}, f"No such folder: {root}")
            return {'CANCELLED'}
        if self.create_folders or is_project(root):
            create_project(root)
        set_current(root, context)
        results.result(self, f"Project: {root}")
        return {'FINISHED'}


class ALLSET_OT_project_window(bpy.types.Operator):
    """Create a project: a folder with Maya's standard sub-folders (Maya File > Project Window)"""
    bl_idname = "allset.project_window"
    bl_label = "Project Window"

    # The Blender notice is this field's tooltip, not a paragraph in the window.
    name: StringProperty(name="Current Project", default=DEFAULT_NAME, description=NOTICE)
    location: StringProperty(name="Location", subtype='DIR_PATH')

    def invoke(self, context, event):
        root = current_root(context)
        self.name, self.location = os.path.basename(root), os.path.dirname(root)
        return context.window_manager.invoke_props_dialog(self, width=DIALOG_WIDTH, confirm_text="Accept")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "name")
        layout.prop(self, "location")
        box = layout.box()
        box.label(text="Primary Project Locations")
        grid = box.grid_flow(columns=3, even_columns=True)
        for folder in FOLDERS:
            grid.label(text=folder, icon='FILE_FOLDER')

    def execute(self, context):
        if not self.name.strip():
            self.report({'ERROR'}, "Give the project a name")
            return {'CANCELLED'}
        root = os.path.join(os.path.abspath(bpy.path.abspath(self.location)), self.name.strip())
        try:
            made = create_project(root)
        except OSError as exc:
            self.report({'ERROR'}, f"Could not create {root}: {exc}")
            return {'CANCELLED'}
        set_current(root, context)
        results.result(self, f"Project {self.name}: {len(made)} folder(s) created in {root}")
        return {'FINISHED'}


class ALLSET_OT_project_recent(bpy.types.Operator):
    """Make this the current project (Maya File > Recent Projects)"""
    bl_idname = "allset.project_recent"
    bl_label = "Recent Project"

    path: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        if not os.path.isdir(self.path):
            self.report({'WARNING'}, f"Project folder is gone: {self.path}")
            return {'CANCELLED'}
        set_current(self.path, context)
        return {'FINISHED'}


class ALLSET_MT_recent_projects(bpy.types.Menu):
    """Recently used projects (Maya File > Recent Projects)"""
    bl_idname = "ALLSET_MT_recent_projects"
    bl_label = "Recent Projects"

    def draw(self, context):
        items = recent(context)
        if not items:
            self.layout.label(text="No recent projects")
        for path in items:
            self.layout.operator("allset.project_recent", text=path, icon='FILE_FOLDER').path = path


# --- operators: open / save -------------------------------------------------------------------------

def browse_from_later(folder, op_idname="WM_OT_open_mainfile", tries=40):
    """Point the file browser that ``op_idname`` opens at ``folder`` once it is there (a few ticks later).
    Blender's Open dialog starts at the most recent file whatever ``filepath`` it is given (Ctrl+O
    goes to Documents), unlike Save As."""
    left = [tries]

    def tick():
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                space = area.spaces.active
                op = getattr(space, "active_operator", None) if area.type == 'FILE_BROWSER' else None
                if op is not None and op.bl_idname == op_idname and space.params is not None:
                    space.params.directory = folder.encode()
                    return None
        left[0] -= 1
        return 0.05 if left[0] > 0 else None
    bpy.app.timers.register(tick, first_interval=0.01)


_OPTION_BOX = BoolProperty(options={'HIDDEN', 'SKIP_SAVE'},
                           description="Maya option box: the file dialog's Options panel shows the settings")


class ALLSET_OT_open_scene(bpy.types.Operator):
    """Open a scene; the file browser starts in the project's scenes folder (Maya Open Scene)"""
    bl_idname = "allset.open_scene"
    bl_label = "Open Scene"

    option_box: _OPTION_BOX

    def invoke(self, context, event):
        path = open_path(context)
        if path:
            result = bpy.ops.wm.open_mainfile('INVOKE_DEFAULT', filepath=path)
            browse_from_later(path)
            return result
        return bpy.ops.wm.open_mainfile('INVOKE_DEFAULT')

    def execute(self, context):
        return self.invoke(context, None)


class ALLSET_OT_save_scene_as(bpy.types.Operator):
    """Save the scene under a new name; the file browser starts in the project's scenes folder
    (Maya Save Scene As)"""
    bl_idname = "allset.save_scene_as"
    bl_label = "Save Scene As"

    option_box: _OPTION_BOX

    def invoke(self, context, event):
        path = save_as_path(context)
        if path:
            return bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT', filepath=path, **_save_args(bpy.ops.wm.save_as_mainfile))
        return bpy.ops.wm.save_as_mainfile('INVOKE_DEFAULT', **_save_args(bpy.ops.wm.save_as_mainfile))

    def execute(self, context):
        return self.invoke(context, None)


def _save_args(op):
    from .. import compat
    return compat.save_dialog_args(op)


class ALLSET_OT_save_scene(bpy.types.Operator):
    """Save the scene; a scene never saved asks for a name in the project's scenes folder (Maya Save Scene)"""
    bl_idname = "allset.save_scene"
    bl_label = "Save Scene"

    def invoke(self, context, event):
        if bpy.data.filepath:
            return bpy.ops.wm.save_mainfile('INVOKE_DEFAULT', **_save_args(bpy.ops.wm.save_mainfile))
        return bpy.ops.allset.save_scene_as('INVOKE_DEFAULT')

    def execute(self, context):
        return self.invoke(context, None)


# --- references ------------------------------------------------------------------------------------------

def unique_namespace(ns, scene):
    """Maya: a namespace already in use gets a number (prop, prop1, prop2 ...)."""
    taken = {c.name for c in scene.collection.children}
    taken |= {o.name.split(":", 1)[0] for o in scene.objects if ":" in o.name}
    if ns not in taken:
        return ns
    n = 1
    while f"{ns}{n}" in taken:
        n += 1
    return f"{ns}{n}"


def _source_name(id_):
    ov = id_.override_library
    ref = ov.reference if ov is not None else None
    return ref.name if ref is not None else id_.name


def reference(path, ns, context, editable=True):
    """Bring the scene of ``path`` in as a reference under the collection ``ns``; returns that collection.

    Linked collections / objects of the source's first scene are put under ``ns``, then (editable) replaced by
    library overrides (``override_hierarchy_create`` needs the linked data in the scene first) whose objects and
    collections are renamed ``ns:name``."""
    scene, view_layer = context.scene, context.view_layer
    with bpy.data.libraries.load(path, link=True) as (src, dst):
        if not src.scenes:
            raise ValueError("no scene in the file")
        dst.scenes = [src.scenes[0]]
    linked = dst.scenes[0]
    group = bpy.data.collections.new(ns)
    scene.collection.children.link(group)
    for coll in list(linked.collection.children):
        group.children.link(coll)
        if editable:
            ov = coll.override_hierarchy_create(scene, view_layer, do_fully_editable=True)
            if ov is not None:
                # the override takes the linked collection's place next to it: drop the original
                if coll in list(group.children):
                    group.children.unlink(coll)
                if ov not in list(group.children):
                    group.children.link(ov)
    for ob in list(linked.collection.objects):
        group.objects.link(ob)
        if editable:
            ov = ob.override_hierarchy_create(scene, view_layer, do_fully_editable=True)
            if ov is not None:
                if ob in list(group.objects):
                    group.objects.unlink(ob)
                if ov not in list(group.objects):
                    group.objects.link(ov)
    if editable:
        # the source's names, not the ".001" Blender gave an override whose name was taken locally (Maya: prop:pCube1)
        for coll in list(group.children_recursive):
            if coll.library is None and not coll.name.startswith(f"{ns}:"):
                coll.name = f"{ns}:{_source_name(coll)}"
        for ob in group.all_objects:
            if ob.library is None and not ob.name.startswith(f"{ns}:"):
                ob.name = f"{ns}:{_source_name(ob)}"
    group["allset_reference"] = path
    return group


class ALLSET_OT_create_reference(bpy.types.Operator):
    """Reference another scene: its objects come in linked and editable (library override), names prefixed
    with the namespace (Maya File > Create Reference; .blend files only)"""
    bl_idname = "allset.create_reference"
    bl_label = "Create Reference"
    bl_options = {'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.blend", options={'HIDDEN'})
    namespace: StringProperty(name="Namespace", description="Name prefix (ns:name); empty = the file name")
    editable: BoolProperty(name="Editable (Library Override)", default=True,
                           description="Make the referenced objects editable; off = linked only, like an "
                                       "unloaded reference you can't change")

    def invoke(self, context, event):
        folder = scenes_dir(context)
        if folder and os.path.isdir(folder) and not self.filepath:
            self.filepath = os.path.join(folder, "")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        path = bpy.path.abspath(self.filepath)
        if not path.lower().endswith(".blend") or not os.path.isfile(path):
            self.report({'ERROR'}, "Blender references .blend files only: use File > Import for .fbx / .obj / .abc / .usd (Maya .ma / .mb can't be read)")
            return {'CANCELLED'}
        if bpy.data.filepath and _norm(path) == _norm(bpy.data.filepath):
            self.report({'ERROR'}, "A scene can't reference itself")
            return {'CANCELLED'}
        ns = (self.namespace.strip() or os.path.splitext(os.path.basename(path))[0]).replace(":", "_")
        from . import references
        node = references.new_node_name(ns, context.scene)       # Maya: propRN, then propRN1
        order = references.next_order(context.scene)
        ns = unique_namespace(ns, context.scene)
        try:
            group = reference(path, ns, context, self.editable)
        except (OSError, ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, f"Could not reference {path}: {exc}")
            return {'CANCELLED'}
        group[references.NODE], group[references.ORDER] = node, order
        if hasattr(context.window_manager, "allset_ref_current"):
            context.window_manager.allset_ref_current = group.name
        results.result(self, f"Referenced {os.path.basename(path)} as {group.name}: "
                              f"{len(group.all_objects)} object(s)")
        return {'FINISHED'}


classes = (ALLSET_OT_set_project, ALLSET_OT_project_window, ALLSET_OT_project_recent, ALLSET_MT_recent_projects,
           ALLSET_OT_open_scene, ALLSET_OT_save_scene_as, ALLSET_OT_save_scene, ALLSET_OT_create_reference)


def register_handlers():
    bpy.app.handlers.save_pre.append(_on_save_pre)
    bpy.app.handlers.load_post.append(_on_load_post)


def unregister_handlers():
    for lst, fn in ((bpy.app.handlers.save_pre, _on_save_pre), (bpy.app.handlers.load_post, _on_load_post)):
        if fn in lst:
            lst.remove(fn)
