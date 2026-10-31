"""L20: pose-mode pick walk (controller tags -> Maya controller
rule; untagged armature -> bones hidden by bone collections are walked past; bones hidden one by one are walked into
like Maya; preference off -> plain DAG) and Control > Tag As Controller /
Parent Controller. The Rigify case counts how many visible controls an Up walks onto a hidden bone, old vs new
(134 / 212 = 63 % before)."""

from importlib import import_module

import addon_utils
import bpy

import kit

joints = import_module(kit.MODULE + ".operators.joints")
controllers = import_module(kit.MODULE + ".operators.controllers")
cb = import_module(kit.MODULE + ".ui.channel_box")
menu_map = import_module(kit.MODULE + ".ui.menu_map")
preferences = import_module(kit.MODULE + ".preferences")

# name: (parent, collection)
TREE = {
    "root": (None, "CTRL"),
    "mch_a": ("root", "MCH"),
    "ctrl_b": ("mch_a", "CTRL"),
    "ctrl_c": ("mch_a", "CTRL"),
    "mch_d": ("mch_a", "MCH"),
    "ctrl_e": ("mch_d", "CTRL"),
    "zz_ctrl": ("root", "CTRL"),
}


def _clear():
    if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm)


def _rig():
    _clear()
    arm = bpy.data.armatures.new("rig")
    ob = bpy.data.objects.new("rig", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    cols = {name: arm.collections.new(name) for name in ("CTRL", "MCH")}
    bpy.ops.object.mode_set(mode='EDIT')
    for i, (name, (parent, _col)) in enumerate(TREE.items()):
        eb = arm.edit_bones.new(name)
        eb.head, eb.tail = (i, 0, 0), (i, 0, 1)
        if parent:
            eb.parent = arm.edit_bones[parent]
    for name, (_parent, col) in TREE.items():
        cols[col].assign(arm.edit_bones[name])
    bpy.ops.object.mode_set(mode='POSE')
    cols["MCH"].is_visible = False
    return ob


def _walk(ob, name, direction, skip=True):
    return joints.walk_bone(ob.data.bones[name], direction, skip).name


def _select(ob, names, active):
    for pb in ob.pose.bones:
        cb.set_bone_selected(pb, pb.name in names)
    ob.data.bones.active = ob.data.bones[active]


def test_hidden_collection_skip():
    ob = _rig()
    assert _walk(ob, "ctrl_b", "UP") == "root" and _walk(ob, "ctrl_e", "UP") == "root"
    assert _walk(ob, "ctrl_b", "UP", skip=False) == "mch_a", "plain DAG walks into the hidden parent"
    assert _walk(ob, "root", "UP") == "root", "no visible ancestor: stays"
    assert _walk(ob, "root", "DOWN") == "ctrl_b", "first of the nearest visible descendants"
    assert _walk(ob, "root", "DOWN", skip=False) == "mch_a"
    # visible siblings under root (depth-first, names sorted per level): ctrl_b, ctrl_c, ctrl_e, zz_ctrl; wraps
    seq, cur = [], "ctrl_b"
    for _ in range(4):
        cur = _walk(ob, cur, "RIGHT")
        seq.append(cur)
    assert seq == ["ctrl_c", "ctrl_e", "zz_ctrl", "ctrl_b"], seq
    assert _walk(ob, "ctrl_b", "LEFT") == "zz_ctrl"
    assert _walk(ob, "ctrl_b", "RIGHT", skip=False) == "ctrl_c" and _walk(ob, "ctrl_c", "RIGHT", skip=False) == "mch_d"
    # the rigger shows the MCH collection: those bones are walked again
    ob.data.collections["MCH"].is_visible = True
    assert _walk(ob, "ctrl_b", "UP") == "mch_a"
    bpy.ops.object.mode_set(mode='OBJECT')


def test_visible_below_order_is_depth_first_by_name():
    ob = _rig()
    order = [b.name for b in joints.visible_below(ob.data.bones["root"].children)]
    # root's children by name: mch_a (hidden -> ctrl_b, ctrl_c, mch_d -> ctrl_e), zz_ctrl
    assert order == ["ctrl_b", "ctrl_c", "ctrl_e", "zz_ctrl"], order
    bpy.ops.object.mode_set(mode='OBJECT')


def test_h_hidden_bone_is_walked_into():
    ob = _rig()
    ob.data.collections["MCH"].is_visible = True
    ob.data.bones["mch_a"].hide = True               # Maya h: pickWalk goes into hidden nodes (M3)
    assert _walk(ob, "ctrl_b", "UP") == "mch_a"
    assert _walk(ob, "root", "DOWN") == "mch_a"
    ob.data.collections["MCH"].is_visible = False
    ob.data.bones["ctrl_c"].hide = True              # hidden one by one in a shown collection: still a sibling
    assert _walk(ob, "ctrl_b", "RIGHT") == "ctrl_c"
    bpy.ops.object.mode_set(mode='OBJECT')


def test_operator_follows_the_preference():
    ob = _rig()
    prefs = preferences.get()
    assert prefs.pick_walk_skip_hidden_collections is True, "on by default"
    try:
        _select(ob, {"ctrl_e"}, "ctrl_e")
        assert bpy.ops.allset.pick_walk_joint(direction="UP") == {'FINISHED'}
        assert cb.lead().name == "root" and [pb.name for pb in cb.targets()] == ["root"]
        prefs.pick_walk_skip_hidden_collections = False
        _select(ob, {"ctrl_e"}, "ctrl_e")
        bpy.ops.allset.pick_walk_joint(direction="UP")
        assert cb.lead().name == "mch_d", "preference off = plain DAG (Maya)"
    finally:
        prefs.pick_walk_skip_hidden_collections = True
    bpy.ops.object.mode_set(mode='OBJECT')


def test_controller_tags():
    ob = _rig()
    bones = ob.data.bones
    # Tag As Controller alone leaves the parent controller empty: Up = DAG parent, hidden or not (Maya M4)
    _select(ob, {"root", "ctrl_e", "ctrl_b"}, "ctrl_e")
    assert bpy.ops.allset.tag_controller() == {'FINISHED'}
    assert all(bones[n].get(joints.CONTROLLER) for n in ("root", "ctrl_e", "ctrl_b"))
    assert joints.has_controllers(ob.data)
    assert _walk(ob, "ctrl_e", "UP") == "mch_d", "tagged armature: no hidden skipping"
    # Parent Controller: the lead (selected last) is the parent
    _select(ob, {"root", "ctrl_e", "ctrl_b"}, "root")
    assert bpy.ops.allset.parent_controller() == {'FINISHED'}
    assert bones["ctrl_e"][joints.CONTROLLER_PARENT] == "root" == bones["ctrl_b"][joints.CONTROLLER_PARENT]
    assert joints.CONTROLLER_PARENT not in bones["root"]
    assert _walk(ob, "ctrl_e", "UP") == "root" and _walk(ob, "ctrl_b", "UP") == "root"
    assert _walk(ob, "root", "DOWN") == "ctrl_b", "first controller child by name"
    assert _walk(ob, "ctrl_b", "RIGHT") == "ctrl_e" and _walk(ob, "ctrl_e", "RIGHT") == "ctrl_b"
    assert _walk(ob, "ctrl_b", "LEFT") == "ctrl_e"
    # an untagged bone in a tagged armature walks the DAG (Maya: no controller -> DAG)
    assert _walk(ob, "ctrl_c", "UP") == "mch_a"
    # no loops: the parent can't become a child of its own controller child
    assert controllers.parent_controllers(bones["ctrl_e"], [bones["root"]]) == 0
    assert joints.CONTROLLER_PARENT not in bones["root"]
    # the operator through the pref-reading path
    _select(ob, {"ctrl_b"}, "ctrl_b")
    bpy.ops.allset.pick_walk_joint(direction="UP")
    assert cb.lead().name == "root"
    bpy.ops.object.mode_set(mode='OBJECT')


def test_controller_warnings():
    ob = _rig()
    _select(ob, {"ctrl_b"}, "ctrl_b")
    assert bpy.ops.allset.parent_controller() == {'CANCELLED'}, "one bone: nothing to parent"
    bpy.ops.object.mode_set(mode='OBJECT')
    assert bpy.ops.allset.tag_controller() == {'CANCELLED'}, "object mode: Maya-style warning"
    assert not joints.has_controllers(ob.data)


def test_menu_rows():
    assert menu_map.MAP["Control/Tag As Controller"] == "allset.tag_controller"
    assert menu_map.MAP["Control/Parent Controller"] == "allset.parent_controller"
    notices = import_module(kit.MODULE + ".ui.notices")
    assert "controller tags" not in notices.CATEGORIES["Control"][1]


def _rigify_rig():
    _clear()
    addon_utils.enable("rigify", default_set=True)
    bpy.ops.object.armature_human_metarig_add()
    meta = bpy.context.object
    bpy.ops.pose.rigify_generate()
    return next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o is not meta)


def test_rigify_up_never_lands_on_hidden_bones():
    try:
        rig = _rigify_rig()
        bones = rig.data.bones
        visible = [b for b in bones if not b.hide and not joints.collection_hidden(b)]
        assert len(visible) > 100, len(visible)

        def lands_hidden(b, direction, skip):
            to = joints.walk_bone(b, direction, skip)
            return to != b and joints.collection_hidden(to)

        counts = {}
        for d in ("UP", "DOWN", "LEFT", "RIGHT"):
            counts[d] = (sum(lands_hidden(b, d, False) for b in visible), sum(lands_hidden(b, d, True) for b in visible))
        stays = sum(joints.walk_bone(b, "UP", True) == b for b in visible)
        n = len(visible)
        for d, (old, new) in counts.items():
            print(f"step217 rigify {d}: old {old}/{n} = {100 * old / n:.1f} %, new {new}/{n} = {100 * new / n:.1f} %")
        print(f"step217 rigify UP stays (no visible ancestor): {stays}/{n}; bones total {len(bones)}")
        assert counts["UP"][0] > n // 3, counts            # the old rule really walked into MCH / ORG bones
        assert all(new == 0 for _old, new in counts.values()), counts
    finally:
        if bpy.context.active_object is not None and bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        addon_utils.disable("rigify", default_set=True)
        _clear()
