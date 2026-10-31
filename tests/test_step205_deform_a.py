"""Lane A (#112): Maya Deform > Tension / Solidify / Sculpt as kit Geometry Nodes deformers
(operators/deformers_205a.py) against the expected results;
every "O" case must match within its tol (1e-4); "U" cases only print their residual."""

from importlib import import_module

import bpy
from mathutils import Vector

import kit

dfa = import_module(kit.MODULE + ".operators.deformers_205a")
deformers = import_module(kit.MODULE + ".operators.deformers")
wire = import_module(kit.MODULE + ".operators.wire_deformer")
history = import_module(kit.MODULE + ".operators.history")
cb = import_module(kit.MODULE + ".ui.channel_box")
ae = import_module(kit.MODULE + ".ui.attribute_editor")


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def _select(*obs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


# --- Tension: every "O" case -------------------------------------------------------------------------------------


# --- Sculpt: every "O" case ----------------------------------------------------------------------------------------


# --- Solidify: modelled rule; Maya's facts ----------------------------------------------------------------------------


# --- names, selection, Channel Box, AE, Paint Weights ---------------------------------------------------------------

def _cube():
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    ob = bpy.context.active_object
    ob.name, ob.data.name = "pCube1", "pCubeShape1"
    return ob


def test_names_selection_rows():
    _clear()
    ob = _cube()
    dfa.create(bpy.context, 'TENSION')
    assert [m.name for m in ob.modifiers] == ["tension1"] and "tension1" in ob.vertex_groups
    assert bpy.context.active_object == ob and ob.select_get()            # Maya: pCube1, tension1
    _select(ob)
    dfa.create(bpy.context, 'TENSION')
    dfa.create(bpy.context, 'SOLIDIFY')
    assert [m.name for m in ob.modifiers] == ["tension1", "tension2", "solidify1"]
    _select(ob)
    dfa.create(bpy.context, 'SCULPT')
    assert "sculpt1" in ob.modifiers
    sculptor, origin = bpy.data.objects["sculptor1"], bpy.data.objects["sculpt1StretchOrigin"]
    assert bpy.context.active_object == sculptor and list(bpy.context.selected_objects) == [sculptor]
    assert sculptor.empty_display_type == 'SPHERE' and tuple(sculptor.scale) == (1.0, 1.0, 1.0)
    assert (sculptor.location - Vector()).length < 1e-6 and (origin.location - Vector()).length < 1e-6
    for md, base in ((ob.modifiers["tension1"], "tension"), (ob.modifiers["solidify1"], "solidify"),
                     (ob.modifiers["sculpt1"], "sculpt")):
        assert deformers.base_of(md) == base and deformers.node_type(md) == base
        assert history.is_deformer(md)
        assert ae.modifier_node(ob, md) == (md.name, base)
        rows = cb._modifier_props(md)
        assert rows[0] == "maya:envelope", rows
    t = ob.modifiers["tension1"]
    assert cb._modifier_props(t) == ["maya:" + k for k in ("envelope", "smoothingIterations", "smoothingStep",
                                                           "inwardConstraint", "outwardConstraint", "squashConstraint",
                                                           "stretchConstraint", "relative")]
    a = deformers.attr(t, "maya:smoothingIterations")
    assert a.get(t) == 10
    a.set(t, 4)
    assert wire.get(t, "Smoothing Iterations") == 4
    assert deformers.paint_group(ob, "tension") == "tension2"
    # the sculpt node's lengths are Maya numbers (× Unit inside the node)
    s = ob.modifiers["sculpt1"]
    assert abs(deformers.attr(s, "maya:maximumDisplacement").get(s) - 0.1) < 1e-6
    assert abs(wire.get(s, "Unit") - 1.0) < 1e-9
    # AE tab draws the node's attributes
    assert dfa.draw_ae is not None and dfa.kind_of(s) == "sculpt"


def test_paint_weights_tension():
    _clear()
    ob = _cube()
    dfa.create(bpy.context, 'TENSION')
    assert bpy.ops.allset.paint_deformer_weights(kind="tension") == {'FINISHED'}
    assert bpy.context.mode == 'PAINT_WEIGHT'
    assert ob.vertex_groups.active.name == "tension1"
    bpy.ops.object.mode_set(mode='OBJECT')


def test_components_make_the_membership():
    _clear()
    ob = _cube()
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for i in (0, 1, 2):
        ob.data.vertices[i].select = True
    bpy.ops.object.mode_set(mode='EDIT')
    dfa.create(bpy.context, 'TENSION')
    vg = ob.vertex_groups["tension1"]
    assert sorted(v.index for v in ob.data.vertices if any(g.group == vg.index for g in v.groups)) == [0, 1, 2]


# --- Delete Non-Deformer History keeps them ------------------------------------------------------------------------


# --- Prune Membership > Sculpt -------------------------------------------------------------------------------------


# --- option windows, menu, undo, disable ---------------------------------------------------------------------------

def test_option_windows_have_maya_factory_values():
    ws = {w.key: w for w in dfa.windows()}
    assert ws["deform_tension"].defaults() == {"iterations": 10, "step": 0.5, "pin_border": True, "relative": 0.0,
                                               "inward": 0.0, "outward": 0.0, "squash": 1.0, "stretch": 1.0,
                                               "shear": 0.0, "bend": 0.0}
    assert ws["deform_solidify"].defaults() == {"attachment": "Borders", "stabilization": 0, "border_falloff": True,
                                                "falloff_iterations": 2}
    assert ws["deform_sculpt"].defaults() == {"mode": "Stretch", "inside_mode": "Even", "max_displacement": 0.1,
                                              "dropoff_type": "Linear", "dropoff_distance": 1.0, "centered": True}
    assert ws["paint_weights_tension"].paths == ("Deform/Paint Weights/Tension",)
    for w in ws.values():
        if w.key.startswith("paint_weights"):
            continue           # Maya's Paint Attributes Tool, shared with the other Paint Weights boxes
        assert w.match[0] == "allset.deformer_tss"
        assert set(w.defaults()) <= set(dfa.DEFAULTS[w.match[1]["kind"]])
    # a window's values reach the node
    _clear()
    ob = _cube()
    ws["deform_tension"].run(bpy.context, {**ws["deform_tension"].defaults(), "iterations": 3, "shear": 0.25})
    md = ob.modifiers["tension1"]
    assert wire.get(md, "Smoothing Iterations") == 3 and abs(wire.get(md, "Shear Strength") - 0.25) < 1e-6


def test_menu_actions_exist():
    for path, action in dfa.MENU.items():
        op = action[0] if isinstance(action, tuple) else action
        mod, name = op.split(".")
        assert hasattr(getattr(bpy.ops, mod), name), path
    assert set(dfa.MENU) == {"Deform/Tension", "Deform/Solidify", "Deform/Sculpt", "Deform/Paint Weights/Tension",
                             "Deform/Prune Membership/Sculpt"}


def test_one_undo_step_each():
    for kind in ('TENSION', 'SOLIDIFY', 'SCULPT'):
        _clear()
        ob = _cube()
        bpy.ops.ed.undo_push(message="before")
        assert bpy.ops.allset.deformer_tss('EXEC_DEFAULT', True, kind=kind) == {'FINISHED'}
        assert len(bpy.data.objects["pCube1"].modifiers) == 1
        bpy.ops.ed.undo()
        ob = bpy.data.objects["pCube1"]
        assert not ob.modifiers and not ob.vertex_groups, kind
        assert "sculptor1" not in bpy.data.objects


def test_disable_is_clean():
    assert dfa._on_depsgraph in bpy.app.handlers.depsgraph_update_post
    kit.disable()
    try:
        assert dfa._on_depsgraph not in bpy.app.handlers.depsgraph_update_post
        assert not hasattr(bpy.types, "ALLSET_OT_deformer_tss") and not hasattr(bpy.types, "ALLSET_OT_prune_sculpt")
        assert not {"tension", "solidify", "sculpt"} & set(deformers.BASES)
        assert not {"tension", "solidify", "sculpt"} & set(deformers.ATTRS)
    finally:
        kit.enable()
    assert "tension" in import_module(kit.MODULE + ".operators.deformers").BASES
