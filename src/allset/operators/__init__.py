# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya-behaviour operators (group, pick-walk, hold/tap snap, pivot, freeze, parent,
duplicate, delete history, create, visibility, ...).

Operator ids use the ``allset.`` prefix. Each module lists its classes in
``classes``; they are registered in that order.
"""

import bpy

from . import (auto_key, bookmarks, ik_fk, component, create, curve_tools, curves_maya, cut_sew, display, driven_key, duplicate, extrude, file_io, freeze, option_windows, fx, global_keys4, graph_keys, graph_key_menu, deformer_weights, joint_labels, group, history, hold, joints, pivot_menu, key_batch, key_batch3, key_insert, loop_pick, manip, marquee,
               anim_layers, lights, light_links, material, menu_extras, menu_items, mesh_maya, multi_cut, poly_maya, rig_maya, mesh_tools, outliner_drag, parenting, pickwalk, pivot, playblast, preselect, project, render_persp, rig_tools, select_convert, select_priority, sets, shading_maps, skin, snap_align, soft_select, symmetry, taphold,
               time_keys, tool_keys, units, uv_shells, uv_tools, uv_modify, uv_select_178, view, view_keys3, visibility)
from . import poly_draw, quad_draw  # step 144 POLY: Create Polygon / Append to Polygon / Quad Draw (#30)
from . import edge_loops  # step 144 LOOP: Insert / Offset Edge Loop, Slide Edge (#31)
from . import ik_rp  # step 245 (#162): Maya ikRPsolver pole vector / twist
from . import joint_edit  # step 243 (#160): joint moves keep Maya frames, Preserve Children, Edit-mode Translate
from . import pivot_pick

classes = (*display.classes, *group.classes, *hold.classes, *taphold.classes,
           *pivot_pick.classes,
           *pickwalk.classes, *view.classes, *freeze.classes, *parenting.classes,
           *duplicate.classes, *history.classes, *create.classes, *visibility.classes,
           *component.classes, *manip.classes, *material.classes,
           *marquee.classes, *preselect.classes, *select_priority.classes, *menu_extras.classes,
           *tool_keys.classes, *symmetry.classes, *pivot.classes, *snap_align.classes, *time_keys.classes,
           *joints.classes, *skin.classes, *driven_key.classes, *rig_tools.classes, *mesh_maya.classes,
           *mesh_tools.classes, *extrude.classes, *uv_tools.classes, *uv_shells.classes, *uv_modify.classes, *light_links.classes, *anim_layers.classes, *uv_select_178.classes, *shading_maps.classes, *fx.classes, *project.classes, *graph_keys.classes, *graph_key_menu.classes, *deformer_weights.classes, *joint_labels.classes, *ik_fk.classes, *playblast.classes, *key_batch.classes, *cut_sew.classes, *multi_cut.classes,
           *outliner_drag.classes, *key_insert.classes, *view_keys3.classes, *global_keys4.classes,
           *pivot_menu.classes, *sets.classes, *menu_items.classes, *file_io.classes, *option_windows.classes,
           *key_batch3.classes, *bookmarks.classes, *curve_tools.classes, *curves_maya.classes,
           *poly_maya.classes, *rig_maya.classes, *loop_pick.classes,
           *render_persp.classes, *select_convert.classes, *poly_draw.classes, *quad_draw.classes,
           *edge_loops.classes)

from . import deformers  # noqa: E402  step 144 DEFORM: Maya Deform menu deformers + Paint Weights (#34)

classes += deformers.classes

from . import default_light, render_batch  # noqa: E402  step 152 RENDER: default light, Test Resolution, Batch (#101)

classes += render_batch.classes

from . import curve_draw  # noqa: E402  step 156 lane T: CV / EP Curve Tool, Three / Two Point Circular Arc

classes += curve_draw.classes

from . import dag  # noqa: E402  step 164: Maya DAG rules for parents (hide / delete / export / isolate)

classes += dag.classes

from . import by_type  # noqa: E402  step 166: Select All by Type for the kit's IK handles / clusters / particles

classes += by_type.classes

from . import modify_maya  # noqa: E402  step 168: Modify menu (Smooth Mesh Preview to Polygons, Evaluate Nodes, ...)

classes += modify_maya.classes

from . import deform_edit  # noqa: E402  step 169: Deform > Wire / ShrinkWrap / Lattice edits, Prune, Point On Curve

classes += deform_edit.classes

from . import select_2d  # noqa: E402  step 170: Maya click / marquee modifiers in Graph / Dope Sheet / UV

classes += select_2d.classes

from . import anim_snapshot  # noqa: E402  step 171: Visualize > Create Animation Snapshot / Update Snapshot

classes += anim_snapshot.classes

from . import repeat_maya  # noqa: E402  step 175: Maya G / Edit > Repeat / Recent Commands for menu commands

classes += repeat_maya.classes

from . import surfaces_maya  # noqa: E402  step 181: Maya Surfaces menu on NURBS surfaces

classes += surfaces_maya.classes

from . import character_sets  # noqa: E402  step 187: Maya Character Sets on Keying Sets

classes += character_sets.classes

from . import color_sets_maya, normals_maya  # noqa: E402  step 189: Mesh Display normals and colour sets

classes += normals_maya.classes + color_sets_maya.classes

from . import poly_cleanup  # noqa: E402  step 197: Mesh > Cleanup... (Maya polyCleanup)

classes += poly_cleanup.classes

from . import graph_buffers, graph_menu_198, graph_retime, graph_weights  # noqa: E402  step 198: Graph Editor depth 2

classes += graph_retime.classes + graph_buffers.classes + graph_weights.classes + graph_menu_198.classes

from . import constrain_199, skin_tools_199  # noqa: E402  step 199: Skin and Constrain tools 2

classes += skin_tools_199.classes + constrain_199.classes
from . import graph_curves_203  # noqa: E402  step 203: Graph Editor curve commands
classes += graph_curves_203.classes
from . import anim_layers_204  # noqa: E402  step 204: animation layers 4
classes += anim_layers_204.classes
from . import pins_205  # noqa: E402  step 205 lane P: UV / Proximity Pin, intermediate objects, wrap influences
classes += pins_205.classes
from . import deformers_205b  # noqa: E402  step 205 lane B: Morph / Jiggle deformers
classes += deformers_205b.classes
from . import deformers_205a  # noqa: E402  step 205 lane A: Tension / Solidify / Sculpt deformers
classes += deformers_205a.classes

from . import uv_206  # noqa: E402  step 206: UV Editor Cycle / Split / Create Shell (Grid) / Auto Seams / UV sets

classes += uv_206.classes

from . import curves_207  # noqa: E402  step 207: Curves > Bend / Curl / Scale Curvature / Lock Length / CV Hardness ...

classes += curves_207.classes

from . import references  # noqa: E402  step 209: Reference Editor commands (reload / unload / replace / import ...)

classes += references.classes

from . import maya_lights  # noqa: E402  step 214: Maya Ambient / Volume Light (no classes: props + handlers)
from . import weight_paint

classes += weight_paint.classes

from . import bake_maya  # noqa: E402  step 217 L18: Maya Bake Simulation (constraints muted, not deleted)

classes += bake_maya.classes

from . import controllers  # noqa: E402  step 217: Control > Tag As Controller / Parent Controller (pick walk)

classes += controllers.classes

from . import deformer_order  # noqa: E402  step 218 L17 / L15b: reorderDeformers, blend shape weight keys

classes += deformer_order.classes
from . import game_exporter, motion_trail  # noqa: E402  step 225
classes += game_exporter.classes
classes += motion_trail.classes
from . import constrain_multi, control_shapes, wire_color  # noqa: E402  step 226 (#136)
classes += control_shapes.classes + wire_color.classes + constrain_multi.classes
from . import constrain_interp  # noqa: E402  step 252 (#168): Maya interpType
classes += constrain_interp.classes
from . import blend_shapes_227, pose_space_227  # noqa: E402  step 227 (#137)
classes += blend_shapes_227.classes + pose_space_227.classes
from . import flow_path_228, motion_path_228  # noqa: E402  step 228 (#138)
classes += motion_path_228.classes + flow_path_228.classes
from . import skeleton_menu  # noqa: E402  step 246 (#163): Insert / Remove / Disconnect / Connect Joint
classes += skeleton_menu.classes
from . import skin_basics  # noqa: E402  step 247 (#164): Prune / Set Max Influences / Go to Bind Pose
classes += skin_basics.classes
from . import joint_display  # noqa: E402  step 248 (#165): Radius row, Local Rotation Axes, Joint Size
classes += joint_display.classes
from . import skin_method  # noqa: E402  step 250 (#167): Weight Blended / DQ skinning method
from . import uv_shell_select  # noqa: E402  step 256 (#172): Maya UV Shell selection in the 3D View / UV Editor
classes += uv_shell_select.classes

_register_classes, _unregister_classes = bpy.utils.register_classes_factory(classes)


def register():
    _register_classes()
    weight_paint.register_props()
    ik_fk.register_props()
    game_exporter.register_props()
    motion_trail.register_props()
    control_shapes.register_props()
    wire_color.register_props()
    constrain_multi.register_props()
    constrain_interp.register_handlers()
    blend_shapes_227.register_props()
    pose_space_227.register_props()
    motion_path_228.register_props()
    flow_path_228.register_props()
    default_light.register()
    joint_edit.register()
    joint_display.register_props()
    skin_method.register_props()
    ik_rp.register_handlers()
    snap_align.register_props()
    material.register_props()
    lights.register_props()
    maya_lights.register()
    light_links.register_props()
    anim_layers.register_props()
    driven_key.register_props()
    mesh_tools.register_props()
    poly_draw.register_props()
    edge_loops.register_props()
    extrude.register_handlers()
    uv_tools.register_props()
    uv_shell_select.register_props()
    fx.register_props()
    taphold.register_bindings()
    graph_keys.register_bindings()
    graph_key_menu.register_bindings()
    deformer_weights.register_bindings()
    joint_labels.register_bindings()
    pivot_menu.register_props()
    sets.register_props()
    view.register_timer()
    units.register_handler()
    tool_keys.register_timer()
    symmetry.register_handler()
    soft_select.register_handlers()
    pivot.register_handler()
    project.register_handlers()
    preselect.register_handlers()
    cut_sew.register_handlers()
    multi_cut.register_handlers()
    poly_draw.register_handlers()
    quad_draw.register_handlers()
    outliner_drag.register_handlers()
    material.register_handlers()
    auto_key.register_handlers()
    dag.register_handlers()
    modify_maya.register_props()
    anim_snapshot.register_handlers()
    repeat_maya.register_handlers()
    character_sets.register_props()
    graph_retime.register_handlers()
    graph_buffers.register_handlers()
    graph_weights.register_handlers()
    graph_menu_198.register_props()
    skin_tools_199.register_handlers()
    constrain_199.register_handlers()
    graph_curves_203.register_handlers()
    pins_205.register_handlers()
    deformers_205b.register_handlers()
    deformers_205a.register_handlers()
    curves_207.register_handlers()


def unregister():
    ik_rp.unregister_handlers()
    joint_edit.unregister()
    joint_display.unregister_props()
    skin_method.unregister_props()
    curves_207.unregister_handlers()
    deformers_205a.unregister_handlers()
    deformers_205b.unregister_handlers()
    pins_205.unregister_handlers()
    graph_curves_203.unregister_handlers()
    constrain_199.unregister_handlers()
    skin_tools_199.unregister_handlers()
    graph_menu_198.unregister_props()
    graph_weights.unregister_handlers()
    graph_buffers.unregister_handlers()
    graph_retime.unregister_handlers()
    weight_paint.unregister_props()
    ik_fk.unregister_props()
    game_exporter.unregister_props()
    motion_trail.unregister_props()
    flow_path_228.unregister_props()
    motion_path_228.unregister_props()
    pose_space_227.unregister_props()
    blend_shapes_227.unregister_props()
    constrain_multi.unregister_props()
    constrain_interp.unregister_handlers()
    wire_color.unregister_props()
    control_shapes.unregister_props()
    character_sets.unregister_props()
    repeat_maya.unregister_handlers()
    anim_snapshot.unregister_handlers()
    select_2d.unregister_timers()
    modify_maya.unregister_props()
    dag.unregister_handlers()
    curve_draw.unregister_handlers()
    auto_key.unregister_handlers()
    material.unregister_handlers()
    outliner_drag.unregister_handlers()
    quad_draw.unregister_handlers()
    poly_draw.unregister_handlers()
    multi_cut.unregister_handlers()
    cut_sew.unregister_handlers()
    project.unregister_handlers()
    pivot.unregister_handler()
    soft_select.unregister_handlers()
    symmetry.unregister_handler()
    tool_keys.unregister_timer()
    marquee.restore_all()
    preselect.clear()
    units.unregister_handler()
    duplicate.PAIRS.clear()
    view.unregister_timer()
    hold.unregister_cleanup()
    joint_labels.unregister_bindings()
    deformer_weights.unregister_bindings()
    graph_key_menu.unregister_bindings()
    graph_keys.unregister_bindings()
    sets.unregister_props()
    pivot_menu.unregister_props()
    taphold.unregister_bindings()
    fx.unregister_props()
    anim_layers.unregister_props()
    light_links.unregister_props()
    maya_lights.unregister()
    lights.unregister_props()
    material.unregister_props()
    uv_shell_select.unregister_props()
    uv_tools.unregister_props()
    extrude.unregister_handlers()
    mesh_tools.clear()
    edge_loops.unregister_props()
    edge_loops.clear()
    poly_draw.unregister_props()
    mesh_tools.unregister_props()
    driven_key.unregister_props()
    snap_align.unregister_props()
    render_batch.unregister()
    default_light.unregister()
    _unregister_classes()

