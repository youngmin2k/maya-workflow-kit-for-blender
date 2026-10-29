# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya symmetric modelling (Status Line Symmetry, Move/Rotate/Scale marking menu Symmetry ▸).

Maya has one global state (``symmetricModelling``): on/off, about object/world/topology,
axis x/y/z; factory default off, x, object. Blender keeps symmetry per mesh
(``Mesh.use_mirror_x/y/z``, ``use_mirror_topology``, local axes through the object
origin), read by edit-mode transforms and sculpt. Design: docs/steps/step_36.md 「계획」.

- The global state lives in ``Scene.allset_symmetry`` (saved with the file; Blender
  user preferences stay untouched).
- ``apply`` writes it to meshes in edit mode; a depsgraph handler applies it to meshes
  entering edit mode and reads back Blender's own header mirror buttons, so the two
  never disagree.
- Axis names are Maya's = Blender's (X = X, Y = Y, Z = Z, like the Channel Box), not
  swapped for Y-up (decision 5). World = the local axis closest to that world axis;
  Blender mirrors through the object origin, so World matches Maya only when the origin
  lies on the world plane (``world_fit`` warns otherwise).
"""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty

AXES = ("X", "Y", "Z")
ABOUT = (("OBJECT", "Object", "Mirror across the object's own axis"),
         ("WORLD", "World", "Mirror across the world axis"),
         ("TOPOLOGY", "Topology", "Mirror by mesh topology (Blender: topology mirror on the chosen axis)"))

# Status Line ▾ list, in Maya's order.
MODES = (("OFF", "Off"),
         ("OBJECT_X", "Object X"), ("OBJECT_Y", "Object Y"), ("OBJECT_Z", "Object Z"),
         ("WORLD_X", "World X"), ("WORLD_Y", "World Y"), ("WORLD_Z", "World Z"),
         ("TOPOLOGY", "Topology"))
# Marking menu check items (Maya's Symmetry submenu in the Move / Rotate / Scale marking menus) and the MMB toggle.
PARTS = (("ON", "Symmetry", "Symmetry on/off"),
         ("ABOUT_WORLD", "World", "Mirror about the world"),
         ("ABOUT_OBJECT", "Object", "Mirror about the object"),
         ("AXIS_X", "X Axis", "Mirror axis X"), ("AXIS_Y", "Y Axis", "Mirror axis Y"),
         ("AXIS_Z", "Z Axis", "Mirror axis Z"),
         ("TOGGLE", "Toggle Symmetry", "Switch between off and the last symmetry mode"))

_EPS = 1e-4


def _partial_changed(_self,_context):
    from . import quad_draw
    quad_draw.clear_topology_preview()


class ALLSET_PG_symmetry(bpy.types.PropertyGroup):
    allow_partial: BoolProperty(name="Allow partial symmetry",default=True,description="Use matched regions for Quad Draw topology symmetry",update=_partial_changed)
    on: BoolProperty(name="Symmetry", default=False)
    about: EnumProperty(name="About", items=ABOUT, default="OBJECT")
    axis: EnumProperty(name="Axis", items=[(a, a, f"{a} axis") for a in AXES], default="X")
    last: EnumProperty(name="Last Mode", items=[(m, l, "") for m, l in MODES[1:]], default="OBJECT_X",
                       options={'HIDDEN'})


def state(scene):
    return scene.allset_symmetry


def mode_of(sym):
    """The Status Line mode id of a state ('OFF', 'OBJECT_X', ..., 'TOPOLOGY')."""
    if not sym.on:
        return "OFF"
    return "TOPOLOGY" if sym.about == 'TOPOLOGY' else f"{sym.about}_{sym.axis}"


def label(sym):
    """Status Line text: Maya's "Symmetry: Off" or the mode name."""
    mode = mode_of(sym)
    return "Symmetry: Off" if mode == "OFF" else dict(MODES)[mode]


def set_mode(sym, mode):
    if mode == "OFF":
        sym.on = False
        return
    if mode == "TOPOLOGY":
        sym.about = 'TOPOLOGY'
    else:
        about, axis = mode.split("_")
        sym.about, sym.axis = about, axis
    sym.on = True


# --- Maya state -> Blender mesh flags ------------------------------------------------

def _closest_local(matrix, world_axis):
    """Index of the local axis whose world direction is closest to ``world_axis`` and
    the cosine between them."""
    m = matrix.to_3x3()
    best, best_cos = 0, -1.0
    for i in range(3):
        col = m.col[i]
        n = col.length
        c = abs(col[world_axis]) / n if n > 0 else 0.0
        if c > best_cos:
            best, best_cos = i, c
    return best, best_cos


def local_axis(ob, sym):
    """Index (0-2) of the mesh axis Blender should mirror for this object."""
    w = AXES.index(sym.axis)
    if sym.about == 'WORLD':
        return _closest_local(ob.matrix_world, w)[0]
    return w


def world_fit(ob, sym):
    """True when Blender's local mirror equals Maya's world symmetry for ``ob``:
    the mirror axis is parallel to the world axis and the origin lies on the world plane."""
    w = AXES.index(sym.axis)
    _i, cos = _closest_local(ob.matrix_world, w)
    return cos > 1 - _EPS and abs(ob.matrix_world.translation[w]) < _EPS


def flags(ob, sym):
    """(use_mirror_x, use_mirror_y, use_mirror_z, use_mirror_topology) for the state."""
    if not sym.on:
        return (False, False, False, False)
    i = local_axis(ob, sym)
    return tuple(i == k for k in range(3)) + (sym.about == 'TOPOLOGY',)


def _mesh_flags(me):
    return (me.use_mirror_x, me.use_mirror_y, me.use_mirror_z, me.use_mirror_topology)


def apply(sym, objects):
    """Write the state to the meshes of ``objects`` (only what differs)."""
    for ob in objects:
        if ob.type != 'MESH':
            continue
        want = flags(ob, sym)
        me = ob.data
        if _mesh_flags(me) != want:
            me.use_mirror_x, me.use_mirror_y, me.use_mirror_z, me.use_mirror_topology = want


def pull(sym, ob):
    """Take the state from a mesh whose mirror flags were changed in Blender's own UI."""
    me = ob.data
    have = _mesh_flags(me)
    if have == flags(ob, sym):
        return False
    on_axes = [k for k in range(3) if have[k]]
    if not on_axes:
        sym.on = False
        return True
    i = on_axes[0]
    if have[3]:
        sym.about = 'TOPOLOGY'
        sym.axis = AXES[i]
    elif sym.about == 'WORLD':
        m = ob.matrix_world.to_3x3()
        col = m.col[i]
        sym.axis = AXES[max(range(3), key=lambda k: abs(col[k]))]
    else:
        sym.about = 'OBJECT'
        sym.axis = AXES[i]
    sym.on = True
    sym.last = mode_of(sym)
    return True


def _editing(scene):
    """Some object of ``scene`` is in edit mode: Blender keeps the active object in the edit mode it shares."""
    for vl in scene.view_layers:
        ob = vl.objects.active
        if ob is not None and ob.mode == 'EDIT':
            return True
    return False


def edit_meshes(scene):
    return [ob for ob in scene.objects if ob.type == 'MESH' and ob.mode == 'EDIT']


def symmetrize_selection(context, sym):
    """Maya SymmetrizeSelection: add the mirror of the selected components."""
    ob = context.edit_object
    if not sym.on or sym.about == 'TOPOLOGY' or ob is None or ob.type != 'MESH':
        return
    try:
        bpy.ops.mesh.select_mirror(axis={AXES[local_axis(ob, sym)]}, extend=True)
    except RuntimeError:
        pass


# --- operator ---------------------------------------------------------------------

def item_state(mode):
    """Check box state of a marking menu item (marking/draw.py)."""
    sym = state(bpy.context.scene)
    if mode == "ON":
        return sym.on
    if mode == "TOPOLOGY":
        return sym.about == 'TOPOLOGY'
    if mode.startswith("ABOUT_"):
        return sym.about == mode[6:]
    if mode.startswith("AXIS_"):
        return sym.axis == mode[5:]
    return mode_of(sym) == mode


class ALLSET_OT_symmetry(bpy.types.Operator):
    """Maya symmetric modelling: edit-mode transforms move the mirrored components too"""
    bl_idname = "allset.symmetry"
    bl_label = "Symmetry"
    bl_options = {'UNDO'}

    mode: EnumProperty(items=[(m, l, "") for m, l in MODES] + list(PARTS))

    @classmethod
    def description(cls, context, props):
        mode = props.mode
        if mode == "OFF":
            return "Turn symmetry off"
        for m, l in MODES:
            if m == mode:
                return f"Symmetry {l}: edit-mode transforms move the mirrored side too"
        return next(p[2] for p in PARTS if p[0] == mode)

    def execute(self, context):
        sym = state(context.scene)
        mode = self.mode
        was_on = sym.on
        if mode == "TOGGLE":     # Maya MMB on the Status Line button: symmetry on / off
            set_mode(sym, "OFF" if sym.on else sym.last)
        elif mode == "ON":       # check box: -symmetry on/off, about/axis kept
            sym.on = not sym.on
        elif mode.startswith("ABOUT_"):
            sym.about = mode[6:]  # Maya: only the About setting, on/off unchanged
        elif mode.startswith("AXIS_"):
            sym.axis = mode[5:]
        else:
            set_mode(sym, mode)
        if sym.on:
            sym.last = mode_of(sym)
        objects = edit_meshes(context.scene)
        apply(sym, objects)
        # Edit Undo records custom data, but not Scene properties. Keep the
        # bound seam's active bit consistent with explicit mode changes.
        from . import quad_draw_symmetry
        import bmesh
        for ob in objects:
            bm=bmesh.from_edit_mesh(ob.data)
            layer=bm.verts.layers.int.get(quad_draw_symmetry.SEED_LAYER)
            if layer is not None:
                active=2 if sym.on and sym.about=='TOPOLOGY' else 0
                for v in bm.verts:
                    if v[layer]:v[layer]=1|active
        # Maya selects the mirrored side when symmetry is switched on.
        if sym.on and (not was_on or mode in dict(MODES)):
            symmetrize_selection(context, sym)
        if sym.on and sym.about == 'WORLD':
            off = [ob.name for ob in objects if not world_fit(ob, sym)]
            from . import quad_draw
            if off and not quad_draw.tool_active(context):
                self.report({'WARNING'}, f"World symmetry mirrors through the object origin: {', '.join(off)} "
                                         f"is not centred on the world {sym.axis} plane")
        return {'FINISHED'}


# --- keep meshes in step with the global state --------------------------------------

_state = {"edit": frozenset()}


@persistent
def _on_depsgraph(scene, _depsgraph):
    try:
        sym = scene.allset_symmetry
    except AttributeError:
        return
    # step 286 (#191): meshes are in edit mode only while the active object is — no scene walk otherwise
    if not _state["edit"] and not _editing(scene):
        return
    edit = edit_meshes(scene)
    names = frozenset(ob.name for ob in edit)
    entered = [ob for ob in edit if ob.name not in _state["edit"]]
    _state["edit"] = names
    if entered:
        apply(sym, entered)
        return
    if edit:
        active = bpy.context.view_layer.objects.active
        ob = active if active in edit else edit[0]
        if pull(sym, ob):
            apply(sym, edit)


@persistent
def _on_load(_dummy):
    _state["edit"] = frozenset()


classes = (ALLSET_PG_symmetry, ALLSET_OT_symmetry)


def register_handler():
    bpy.types.Scene.allset_symmetry = bpy.props.PointerProperty(type=ALLSET_PG_symmetry)
    _state["edit"] = frozenset()
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    bpy.app.handlers.load_post.append(_on_load)


def unregister_handler():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    del bpy.types.Scene.allset_symmetry
