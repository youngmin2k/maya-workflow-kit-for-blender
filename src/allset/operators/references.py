# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya references on Blender links + library overrides (Issue #116).

A kit reference (``project.reference``) is a collection named after its namespace, marked ``REF`` (the
source path) and ``NODE`` (Maya's reference node name, propRN / propRN1), holding library overrides of the source
file's first scene. Maya's rules:

- Reload keeps the reference edits and shows the source's other changes = ``Library.reload()`` (an edited attribute
  hides the source's change of that attribute in both programs: Maya's edit is a whole-attribute setAttr, Blender's
  override operation covers the whole ``location`` array).
- Unload: the nodes go, the edits stay; Load brings both back = the namespace's layer collection excluded / included
  (the overrides are kept; Blender has no unloaded state, the data stays in memory).
- Replace: the new file comes in under the same namespace and the edits are applied again by node name.
- Import Objects from Reference: the nodes become local with their ``ns:`` names = ``make_local(clear_liboverride=True)``.
- Remove: nodes and namespace go (the library too when no other reference uses it).
- Lock: no edits = ``override_library.is_system_override``; Clean Up = ``override_library.reset()``.
- Offline files (Maya ``.editMA`` = the reference edits): a JSON of the edits by source node name.
"""

import json
import os
import re

import bpy
from bpy.props import EnumProperty, StringProperty

from .. import results

REF = "allset_reference"            # on the namespace collection: the source path
NODE = "allset_reference_node"      # Maya's reference node name: propRN, propRN1
ORDER = "allset_reference_order"    # creation order (the Reference Editor lists references like Maya)
REPLACED = "allset_reference_replaced"   # Recently Replaced Files (newest first)
LOCKED = "allset_reference_locked"
OFFLINE_EXT = ".json"


# --- the model ------------------------------------------------------------------------------------------------------

def references(scene=None):
    """Kit references of ``scene`` (its collection tree), in creation order."""
    scene = scene or bpy.context.scene
    out = [c for c in scene.collection.children_recursive if c.get(REF) and c.library is None]
    return sorted(out, key=lambda c: (c.get(ORDER, 0), c.name))


def find(name, scene=None):
    """A reference by namespace or reference node name."""
    for ref in references(scene):
        if name in (ref.name, node_name(ref)):
            return ref
    return None


def node_name(ref):
    return ref.get(NODE) or f"{ref.name}RN"


def new_node_name(requested, scene=None):
    """Maya: the first ``prop`` reference is propRN, the next one (namespace prop1) propRN1."""
    taken = {node_name(r) for r in references(scene)}
    base = f"{requested}RN"
    if base not in taken:
        return base
    n = 1
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def next_order(scene=None):
    return 1 + max((r.get(ORDER, 0) for r in references(scene)), default=0)


def path_of(ref):
    return ref.get(REF, "")


def file_label(ref):
    return os.path.basename(path_of(ref))


def ids(ref):
    """Every ID the reference brought in: collections, objects and their data (overrides or linked)."""
    out = []
    seen = set()
    for idb in [*ref.children_recursive, *ref.all_objects]:
        for x in (idb, getattr(idb, "data", None)):
            if x is not None and x.as_pointer() not in seen and (x.override_library is not None or x.library):
                seen.add(x.as_pointer())
                out.append(x)
    return out


def library(ref):
    for idb in ids(ref):
        ov = idb.override_library
        if ov is not None and ov.reference is not None and ov.reference.library is not None:
            return ov.reference.library
        if idb.library is not None:
            return idb.library
    return None


def layer_collection(ref, view_layer=None):
    view_layer = view_layer or bpy.context.view_layer

    def walk(lc):
        if lc.collection == ref:
            return lc
        for ch in lc.children:
            hit = walk(ch)
            if hit is not None:
                return hit
        return None
    return walk(view_layer.layer_collection)


def is_loaded(ref, view_layer=None):
    lc = layer_collection(ref, view_layer)
    return lc is not None and not lc.exclude


def set_loaded(ref, loaded, view_layer=None):
    """Unload / Load: the namespace's layer collection excluded / included (the edits stay)."""
    lc = layer_collection(ref, view_layer)
    if lc is None:
        return False
    lc.exclude = not loaded
    return True


def is_locked(ref):
    return bool(ref.get(LOCKED))


def set_locked(ref, locked):
    for idb in ids(ref):
        if idb.override_library is not None:
            idb.override_library.is_system_override = bool(locked)
    ref[LOCKED] = bool(locked)


def reload(ref):
    lib = library(ref)
    if lib is None:
        raise RuntimeError(f"{node_name(ref)} has no linked library")
    lib.reload()
    return lib.filepath


def _source_name(idb):
    ov = idb.override_library
    if ov is not None and ov.reference is not None:
        return ov.reference.name
    return idb.name.split(":", 1)[-1]


def _plain(value):
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bpy.types.ID) or value is None:
        return None
    try:
        items = list(value)
    except TypeError:
        return None
    flat = []
    for v in items:
        if isinstance(v, (bool, int, float)):
            flat.append(v)
        else:
            try:
                flat.append([float(x) for x in v])
            except TypeError:
                return None
    return flat


def edits(ref):
    """The reference edits as [(source name, ID type, rna path, value)] (Maya listReferenceEdits): every overridden
    property with a plain value, current values."""
    out = []
    for idb in ids(ref):
        ov = idb.override_library
        if ov is None:
            continue
        ov.operations_update()
        for prop in ov.properties:
            path = prop.rna_path
            try:
                value = _plain(idb.path_resolve(path))
            except (ValueError, AttributeError):
                continue
            if value is not None:
                out.append((_source_name(idb), type(idb).__name__, path, value))
    return out


_INDEX = re.compile(r"^(.*)\[(\d+)\]$")
_KEY = re.compile(r'^(.*)\["(.+)"\]$')
_ATTR = re.compile(r"^(?:(.*)\.)?([A-Za-z_]\w*)$")


def set_path(idb, path, value):
    """Write ``value`` at the RNA ``path`` of ``idb`` (``location``, ``modifiers["x"].levels``, ``["prop"]``)."""
    m = _KEY.match(path)
    if m:
        owner = idb.path_resolve(m.group(1)) if m.group(1) else idb
        owner[m.group(2)] = value
        return
    m = _INDEX.match(path)
    if m:
        idb.path_resolve(m.group(1))[int(m.group(2))] = value
        return
    m = _ATTR.match(path)
    if m is None:
        raise ValueError(path)
    owner = idb.path_resolve(m.group(1)) if m.group(1) else idb
    setattr(owner, m.group(2), value)


def apply_edits(ref, rows):
    """Apply recorded edits by source node name (Maya re-applies reference edits by node name). Count applied."""
    by_name = {}
    for idb in ids(ref):
        if idb.override_library is not None:
            by_name.setdefault((_source_name(idb), type(idb).__name__), idb)
    done = 0
    for name, kind, path, value in rows:
        idb = by_name.get((name, kind))
        if idb is None:
            continue
        try:
            set_path(idb, path, value)
            done += 1
        except (ValueError, AttributeError, TypeError, KeyError, IndexError):
            pass
    return done


def clean_up(ref):
    """Maya Clean Up Reference: drop every edit (the overrides go back to the source's values)."""
    n = 0
    for idb in ids(ref):
        if idb.override_library is not None:
            idb.override_library.reset()
            n += 1
    return n


def _drop_library(lib, scene=None):
    if lib is None:
        return
    if any(library(r) == lib for r in references(scene)):
        return
    try:
        bpy.data.libraries.remove(lib)
    except (RuntimeError, ReferenceError):
        pass


def remove(ref, scene=None):
    """Maya Remove Reference: the referenced nodes and the namespace go."""
    lib = library(ref)
    things = ids(ref)
    colls = [c for c in ref.children_recursive]
    for ob in list(ref.all_objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in reversed(colls):
        try:
            bpy.data.collections.remove(c)
        except (RuntimeError, ReferenceError):
            pass
    bpy.data.collections.remove(ref)
    for idb in things:
        try:
            if idb.users == 0 and idb.library is None:
                getattr(bpy.data, _COLLECTION.get(type(idb).__name__, ""), None).remove(idb)
        except (AttributeError, ReferenceError, RuntimeError):
            pass
    _drop_library(lib, scene)


_COLLECTION = {"Mesh": "meshes", "Curve": "curves", "Camera": "cameras", "Light": "lights", "Armature": "armatures",
               "Lattice": "lattices", "Material": "materials", "SurfaceCurve": "curves", "TextCurve": "curves"}


def import_objects(ref, scene=None):
    """Maya Import Objects from Reference: everything becomes local, ``ns:`` names kept, the reference node goes."""
    lib = library(ref)
    n = 0
    for idb in ids(ref):
        try:
            if idb.override_library is not None:
                idb.make_local(clear_liboverride=True)      # in place: name and edited values kept
                n += 1
            elif isinstance(idb, bpy.types.Object):
                n += idb.make_local() is not None
        except RuntimeError:
            pass
    members = list(ref.all_objects)
    for linked in {ob.data for ob in members if ob.data is not None and ob.data.library is not None}:
        # linked data (an override object's mesh) may be shared with another reference of the same file: a local
        # copy for this reference's objects only (make_local() would remap every user)
        try:
            local = linked.copy()
            local.name = linked.name
            for ob in members:
                if ob.data == linked:
                    ob.data = local
            n += 1
        except RuntimeError:
            pass
    for ob in list(ref.all_objects):
        data = ob.data
        for i, mat in enumerate(getattr(data, "materials", ())):
            if mat is not None and mat.library is not None:
                data.materials[i] = mat.make_local()     # the shading stays when the library goes
    for key in (REF, NODE, ORDER, REPLACED, LOCKED):
        if key in ref:
            del ref[key]
    _drop_library(lib, scene)
    return n


def replace(ref, path, context):
    """Maya Replace Reference: ``path`` under the same namespace, loaded state and node name, edits re-applied."""
    from . import project
    rows = edits(ref)
    ns, node, order, loaded = ref.name, node_name(ref), ref.get(ORDER, 0), is_loaded(ref)
    history = [p for p in list(ref.get(REPLACED, [])) if p != path]
    old = path_of(ref)
    editable = any(i.override_library is not None for i in ids(ref))
    parent = next((c for c in [context.scene.collection, *context.scene.collection.children_recursive]
                   if ref.name in c.children), context.scene.collection)
    remove(ref, context.scene)
    new = project.reference(path, ns, context, editable)
    if parent is not context.scene.collection:
        context.scene.collection.children.unlink(new)
        parent.children.link(new)
    new[NODE], new[ORDER] = node, order
    new[REPLACED] = ([old] + history)[:10]
    applied = apply_edits(new, rows)
    if not loaded:
        set_loaded(new, False)
    return new, applied


def duplicate(ref, context):
    from . import project
    base = re.sub(r"\d+$", "", ref.name) or ref.name
    ns = project.unique_namespace(base, context.scene)
    new = project.reference(path_of(ref), ns, context, any(i.override_library is not None for i in ids(ref)))
    new[NODE] = new_node_name(base, context.scene)
    new[ORDER] = next_order(context.scene)
    return new


def related(objects, scene=None):
    """References holding any of ``objects`` (Maya Load / Unload Related References)."""
    out = []
    for ref in references(scene):
        members = set(ref.all_objects)
        if any(ob in members for ob in objects):
            out.append(ref)
    return out


def export_edits(ref, path):
    rows = edits(ref)
    data = {"reference": node_name(ref), "namespace": ref.name, "file": path_of(ref),
            "edits": [{"node": n, "type": t, "path": p, "value": v} for n, t, p, v in rows]}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    return len(rows)


def assign_edits(ref, path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = [(e["node"], e["type"], e["path"], e["value"]) for e in data.get("edits", [])]
    return apply_edits(ref, rows)


# --- operators --------------------------------------------------------------------------------------------------------

def current(context):
    """The Reference Editor's selected reference, else the only one, else None."""
    wm = context.window_manager
    name = getattr(wm, "allset_ref_current", "")
    ref = find(name, context.scene) if name else None
    if ref is None:
        refs = references(context.scene)
        ref = refs[0] if len(refs) == 1 else None
    return ref


ACTIONS = (("RELOAD", "Reload Reference", "Reload the selected reference (edits kept)"),
           ("UNLOAD", "Unload Reference", "Unload the selected reference (its edits are kept)"),
           ("LOAD", "Load Reference", "Load the selected reference"),
           ("TOGGLE", "Load / Unload", "Load or unload the reference"),
           ("IMPORT", "Import Objects from Reference", "Make the reference's objects local, names kept"),
           ("REMOVE", "Remove Reference", "Remove the selected reference and its objects"),
           ("DUPLICATE", "Duplicate Reference", "Reference the same file again (next namespace)"),
           ("LOCK", "Lock Reference", "Lock the selected reference: no edits"),
           ("UNLOCK", "Unlock Reference", "Unlock the selected reference"),
           ("CLEAN", "Clean Up Reference", "Remove all edits to the selected reference"),
           ("SELECT", "Select File Contents", "Select the objects that came from the selected reference"),
           ("LOAD_RELATED", "Load Related References", "Load the references of the selected objects"),
           ("UNLOAD_RELATED", "Unload Related References", "Unload the references of the selected objects"),
           ("LIST", "List Reference Edits", "List the edits made to the selected reference"))


class ALLSET_OT_reference_cmd(bpy.types.Operator):
    """Maya Reference Editor command on the selected reference"""
    bl_idname = "allset.reference_cmd"
    bl_label = "Reference"
    bl_options = {'UNDO'}

    action: EnumProperty(items=ACTIONS, name="Action", options={'SKIP_SAVE'})
    reference: StringProperty(name="Reference", description="Namespace or reference node (empty = selected)",
                              options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, props):
        return next((d for k, _l, d in ACTIONS if k == props.action), "")

    def execute(self, context):
        scene = context.scene
        if self.action in {"LOAD_RELATED", "UNLOAD_RELATED"}:
            refs = related(context.selected_objects, scene)
            if not refs:
                self.report({'WARNING'}, "No referenced objects selected")
                return {'CANCELLED'}
            for ref in refs:
                set_loaded(ref, self.action == "LOAD_RELATED")
            results.result(self, f"{'Loaded' if self.action == 'LOAD_RELATED' else 'Unloaded'} "
                                 f"{', '.join(node_name(r) for r in refs)}")
            return {'FINISHED'}
        ref = find(self.reference, scene) if self.reference else current(context)
        if ref is None:
            self.report({'WARNING'}, "Select a reference in the Reference Editor")
            return {'CANCELLED'}
        rn = node_name(ref)
        a = self.action
        if a == "TOGGLE":
            a = "UNLOAD" if is_loaded(ref) else "LOAD"
        try:
            if a == "RELOAD":
                set_loaded(ref, True)
                path = reload(ref)
                results.result(self, f"Reloaded {rn}: {os.path.basename(path)}")
            elif a in {"UNLOAD", "LOAD"}:
                set_loaded(ref, a == "LOAD")
                results.result(self, f"{'Loaded' if a == 'LOAD' else 'Unloaded'} {rn}")
            elif a == "IMPORT":
                n = import_objects(ref, scene)
                results.result(self, f"Imported {n} node(s) from {rn}")
            elif a == "REMOVE":
                remove(ref, scene)
                context.window_manager.allset_ref_current = ""
                results.result(self, f"Removed {rn}")
            elif a == "DUPLICATE":
                new = duplicate(ref, context)
                context.window_manager.allset_ref_current = new.name
                results.result(self, f"Referenced {file_label(new)} as {node_name(new)}")
            elif a in {"LOCK", "UNLOCK"}:
                set_locked(ref, a == "LOCK")
                results.result(self, f"{'Locked' if a == 'LOCK' else 'Unlocked'} {rn}")
            elif a == "CLEAN":
                if is_loaded(ref):
                    # Maya: "Clean Up Reference" works on an unloaded reference only
                    self.report({'WARNING'}, f"Unload {rn} before cleaning up its edits")
                    return {'CANCELLED'}
                n = clean_up(ref)
                results.result(self, f"Removed the edits of {n} node(s) in {rn}")
            elif a == "SELECT":
                for ob in context.view_layer.objects:
                    if ob is not None:
                        ob.select_set(False)
                obs = [o for o in ref.all_objects if o.name in context.view_layer.objects]
                for ob in obs:
                    ob.select_set(True)
                if obs:
                    context.view_layer.objects.active = obs[-1]
                results.result(self, f"Selected {len(obs)} object(s) of {rn}")
            elif a == "LIST":
                rows = edits(ref)
                _LAST_LIST[:] = [f"{n}.{p} = {v}" for n, _t, p, v in rows]
                results.result(self, f"{rn}: {len(rows)} edit(s)")
                if context.window_manager.windows and not bpy.app.background:
                    context.window_manager.popup_menu(_draw_list, title=f"Reference Edits: {rn}", icon='LINKED')
        except (RuntimeError, OSError, ValueError) as exc:
            self.report({'ERROR'}, f"{rn}: {exc}")
            return {'CANCELLED'}
        return {'FINISHED'}


_LAST_LIST = []


def _draw_list(self, _context):
    col = self.layout.column()
    for line in _LAST_LIST[:40] or ["No edits"]:
        col.label(text=line)
    if len(_LAST_LIST) > 40:
        col.label(text=f"... {len(_LAST_LIST) - 40} more")


class _PickRef:
    reference: StringProperty(options={'SKIP_SAVE'})

    def target(self, context):
        return find(self.reference, context.scene) if self.reference else current(context)


class ALLSET_OT_reference_replace(_PickRef, bpy.types.Operator):
    """Replace the file of the selected reference (its edits are applied again by node name)"""
    bl_idname = "allset.reference_replace"
    bl_label = "Replace Reference"
    bl_options = {'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: StringProperty(default="*.blend", options={'HIDDEN'})

    def invoke(self, context, event):
        ref = self.target(context)
        if ref is None:
            self.report({'WARNING'}, "Select a reference in the Reference Editor")
            return {'CANCELLED'}
        self.reference = ref.name
        if not self.filepath:
            self.filepath = path_of(ref)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        ref = self.target(context)
        path = bpy.path.abspath(self.filepath)
        if ref is None or not path.lower().endswith(".blend") or not os.path.isfile(path):
            self.report({'ERROR'}, "Pick a .blend file to reference")
            return {'CANCELLED'}
        try:
            new, n = replace(ref, path, context)
        except (OSError, ValueError, RuntimeError) as exc:
            self.report({'ERROR'}, f"Could not replace {node_name(ref)}: {exc}")
            return {'CANCELLED'}
        context.window_manager.allset_ref_current = new.name
        results.result(self, f"Replaced {node_name(new)} with {os.path.basename(path)}: {n} edit(s) applied")
        return {'FINISHED'}


class ALLSET_OT_reference_offline(_PickRef, bpy.types.Operator):
    """Maya Export to Offline File / Assign Offline File: the selected reference's edits to / from a file"""
    bl_idname = "allset.reference_offline"
    bl_label = "Offline File"
    bl_options = {'UNDO'}

    mode: EnumProperty(items=(("EXPORT", "Export", "Export the reference edits to a file"),
                              ("ASSIGN", "Assign", "Apply the edits of a file to the reference")),
                       options={'SKIP_SAVE'})
    filepath: StringProperty(subtype='FILE_PATH', options={'SKIP_SAVE'})
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    @classmethod
    def description(cls, context, props):
        return ("Export the selected reference's edits to an offline file (JSON)" if props.mode == "EXPORT" else
                "Apply the edits of an offline file (JSON) to the selected reference")

    def invoke(self, context, event):
        ref = self.target(context)
        if ref is None:
            self.report({'WARNING'}, "Select a reference in the Reference Editor")
            return {'CANCELLED'}
        self.reference = ref.name
        if not self.filepath:
            folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.dirname(path_of(ref))
            self.filepath = os.path.join(folder, f"{node_name(ref)}_edits{OFFLINE_EXT}")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        ref = self.target(context)
        if ref is None:
            return {'CANCELLED'}
        path = bpy.path.abspath(self.filepath)
        try:
            if self.mode == "EXPORT":
                n = export_edits(ref, path)
                results.result(self, f"Exported {n} edit(s) of {node_name(ref)} to {os.path.basename(path)}")
            else:
                n = assign_edits(ref, path)
                results.result(self, f"Assigned {n} edit(s) from {os.path.basename(path)} to {node_name(ref)}")
        except (OSError, ValueError, KeyError) as exc:
            self.report({'ERROR'}, f"Offline file: {exc}")
            return {'CANCELLED'}
        return {'FINISHED'}


class ALLSET_OT_reference_recent(_PickRef, bpy.types.Operator):
    """Replace the reference with a file it held before (Maya Recently Replaced Files)"""
    bl_idname = "allset.reference_recent"
    bl_label = "Recently Replaced File"
    bl_options = {'UNDO'}

    filepath: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        ref = self.target(context)
        if ref is None or not os.path.isfile(self.filepath):
            self.report({'WARNING'}, "That file isn't there any more")
            return {'CANCELLED'}
        new, n = replace(ref, self.filepath, context)
        context.window_manager.allset_ref_current = new.name
        results.result(self, f"Replaced {node_name(new)} with {os.path.basename(self.filepath)}: {n} edit(s) applied")
        return {'FINISHED'}


class ALLSET_MT_reference_recent(bpy.types.Menu):
    bl_idname = "ALLSET_MT_reference_recent"
    bl_label = "Recently Replaced Files"

    def draw(self, context):
        ref = current(context)
        paths = list(ref.get(REPLACED, [])) if ref is not None else []
        if not paths:
            self.layout.label(text="No replaced files")
        for p in paths:
            op = self.layout.operator(ALLSET_OT_reference_recent.bl_idname, text=os.path.basename(p))
            op.filepath, op.reference = p, ref.name


classes = (ALLSET_OT_reference_cmd, ALLSET_OT_reference_replace, ALLSET_OT_reference_offline,
           ALLSET_OT_reference_recent, ALLSET_MT_reference_recent)
