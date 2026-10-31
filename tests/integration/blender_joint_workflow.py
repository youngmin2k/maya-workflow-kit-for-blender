"""Run: Blender --background --factory-startup --python tests/blender_joint_workflow.py"""
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2] / 'src' / 'allset'
sys.path.insert(0, str(ROOT.parent))
addon = importlib.import_module(ROOT.name)
from allset.operators import joint_selection as selection, joints, tool_keys, component
from allset.ui.channel_box import bone_selected

for cls in (component.ALLSET_OT_select_none, tool_keys.ALLSET_OT_toggle_sel_mode):
    bpy.utils.register_class(cls)

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
rig = joints.new_skeleton(bpy.context)
a = joints.add_joint(rig, (0, 0, 0))
b = joints.add_joint(rig, (0, 0, 2), a)
joints.finish(bpy.context, rig, [a, b])
bpy.ops.object.mode_set(mode='OBJECT')
mesh = bpy.data.objects.new('other', bpy.data.meshes.new('other'))
bpy.context.collection.objects.link(mesh)

def selected():
    return {pb.name for pb in rig.pose.bones if bone_selected(pb)}

# Picking joints enters pose directly and applies each Maya modifier.
selection.select(bpy.context, rig, a)
assert bpy.context.mode == 'POSE' and selected() == {a}
selection.select(bpy.context, rig, b, shift=True, ctrl=True)
assert selected() == {a, b}
selection.select(bpy.context, rig, b, shift=True, ctrl=True)
assert selected() == {a, b}, 'add must never toggle off'
selection.select(bpy.context, rig, a, ctrl=True)
assert selected() == {b}
selection.select(bpy.context, rig, a, ctrl=True)
assert selected() == {b}, 'subtract must never add'
selection.select(bpy.context, rig, a, shift=True)
assert selected() == {a, b}
selection.select(bpy.context, rig, a, shift=True)
assert selected() == {b}
selection.select(bpy.context, rig, b, shift=True)
assert not selected() and bpy.context.mode == 'OBJECT'
assert bpy.context.active_object is None

# Replacing a joint selection clears a previously selected mesh.
mesh.select_set(True)
bpy.context.view_layer.objects.active = mesh
selection.select(bpy.context, rig, a)
assert not mesh.select_get() and selected() == {a}
# F8 goes from joint object state to rest-skeleton components and back.
bpy.ops.allset.toggle_sel_mode()
assert bpy.context.mode == 'EDIT_ARMATURE'
# Projection picking works in Edit mode as well as Pose mode.
ctx = SimpleNamespace(region=SimpleNamespace(width=200, height=200),
                      region_data=SimpleNamespace(perspective_matrix=Matrix.Identity(4)))
assert selection.pick(ctx, rig, (100, 100), 6) is not None
bpy.ops.allset.toggle_sel_mode()
assert bpy.context.mode == 'POSE'
assert selection.pick(ctx, rig, (100, 100), 6) is not None
# Alt+D clears pose, object, active, and latent selection.
bpy.ops.allset.select_none()
assert bpy.context.mode == 'OBJECT' and not selected()
assert not bpy.context.selected_objects and bpy.context.active_object is None
# Same command releases armature Edit mode.
selection.select(bpy.context, rig, a)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.allset.select_none()
assert bpy.context.mode == 'OBJECT' and bpy.context.active_object is None
assert not selected()

# A different rig switches automatically; old selected bones are cleared on replace.
second = joints.new_skeleton(bpy.context)
c = joints.add_joint(second, (4, 0, 0))
joints.finish(bpy.context, second, [c])
selection.select(bpy.context, rig, a)
assert bpy.context.active_object == rig and bpy.context.mode == 'POSE'
assert not any(bone_selected(pb) for pb in second.pose.bones)
# Maya never branches from a joint picked before the Joint Tool starts:
# the tool starts a new chain; cancelling before placement preserves the selection.
status = []
proxy = SimpleNamespace(window=bpy.context.window, active_object=rig,
                        workspace=SimpleNamespace(status_text_set=status.append),
                        window_manager=SimpleNamespace(modal_handler_add=lambda op: None))
class _ToolState(SimpleNamespace):
    # stand-in operator instance: methods and class values come from the Joint Tool itself
    def __getattr__(self, name):
        value = getattr(joints.ALLSET_OT_joint_tool, name)
        return value.__get__(self) if callable(value) and hasattr(value, '__get__') else value


state = _ToolState()
off_screen = SimpleNamespace(mouse_x=-10000, mouse_y=-10000)
assert joints.ALLSET_OT_joint_tool.invoke(state, proxy, off_screen) == {'RUNNING_MODAL'}
assert state._ob is None and state._parent is None and bpy.context.mode == 'POSE'
state._end = lambda context: joints.ALLSET_OT_joint_tool._end(state, context)
assert joints.ALLSET_OT_joint_tool._done(state, proxy) == {'CANCELLED'}
assert selected() == {a} and bpy.context.mode == 'POSE'
# Q exits the placement modal instead of letting future clicks keep adding joints
# (nothing placed yet: the modal ends CANCELLED, like Enter).
# the real _done ends CANCELLED while nothing was placed, FINISHED once a chain exists
state._done = lambda context: {'CANCELLED'} if state._ob is None else {'FINISHED'}
# #158: the modal finds a 3D view itself (view under the mouse, else any) — the stand-in needs it
state._any_view = joints.ALLSET_OT_joint_tool._any_view
event = SimpleNamespace(type='Q', value='PRESS', alt=False, ctrl=False,
                        shift=False, oskey=False, mouse_x=-1, mouse_y=-1)
assert joints.ALLSET_OT_joint_tool.modal(state, bpy.context, event) == {'CANCELLED'}
state._ob = rig
assert joints.ALLSET_OT_joint_tool.modal(state, bpy.context, event) == {'FINISHED'}

# An object row can release Edit mode without a manual Tab/F8.
from allset.ui import outliner
bpy.ops.object.mode_set(mode='EDIT')
row = SimpleNamespace(kind='OBJECT', object=mesh.name)
outliner.select_rows(bpy.context, [row], 0, 'REPLACE')
assert bpy.context.mode == 'OBJECT' and bpy.context.active_object == mesh
assert not selected()

# Generated bindings route all Select None states to the same implementation.
data = addon.keymap.generate_data()
from allset.keymap import mapping, patch
assert mapping.check_entry(patch.KeyconfigData(data), {'key': 'd', 'modifiers': ['alt']},
                           mapping.ENTRIES['SelectNone']), 'Select None mapping must match the installed shortcut'
for name in ('Object Mode', 'Pose', 'Armature'):
    km = next(k for k in data if k[0] == name)
    items = [i for i in km[2]['items'] if i[1]['type'] == 'D' and i[1].get('alt')]
    assert any(i[0] == 'allset.select_none' for i in items), (name, items)
print('PASS: Maya joint workflow integration checks')
