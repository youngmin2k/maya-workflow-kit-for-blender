# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya Skeleton > Joint Labelling and Enable / Disable Selected IK Handles.

Behaviour: Maya 2022 menus.

A Maya joint is a bone. Its joint label attributes live as ID properties on the bone: ``allset_side``
(Maya ``side``: 0 Center, 1 Left, 2 Right, 3 None; factory 0), ``allset_type`` (Maya ``type``, the 30-value enum
below; factory 0 None), ``allset_other_type`` (Maya ``otherType``, factory "jaw") and ``allset_draw_label``
(``drawLabel``, factory off). In armature edit mode they are written on the edit bone (Blender writes edit bones
back over the bones when edit mode ends), else on the data bone.

Which joints a command acts on follows Maya's ``cmds.ls(selection=True, type="joint"[, dag=True])``: the selected
joints (pose bones in pose mode, edit bones in edit mode; in object mode a selected skeleton stands for its root
joints) and, for the ``dag`` commands, everything below them.
"""

import blf
import bpy
import gpu
from bpy.props import BoolProperty, EnumProperty
from bpy_extras import view3d_utils

SIDE, TYPE, OTHER, DRAW = "allset_side", "allset_type", "allset_other_type", "allset_draw_label"
OTHER_DEFAULT = "jaw"          # a new joint's otherType

# Maya joint.side enum: index = value
SIDES = ("Center", "Left", "Right", "None")
CENTER, LEFT, RIGHT, NO_SIDE = range(4)
# Maya joint.type enum: index = value
TYPES = ("None", "Root", "Hip", "Knee", "Foot", "Toe", "Spine", "Neck", "Head", "Collar", "Shoulder", "Elbow", "Hand",
         "Finger", "Thumb", "PropA", "PropB", "PropC", "Other", "Index Finger", "Middle Finger", "Ring Finger",
         "Pinky Finger", "Extra Finger", "Big Toe", "Index Toe", "Middle Toe", "Ring Toe", "Pinky Toe", "Foot Thumb")
T_NONE, T_ROOT, T_HIP, T_KNEE, T_FOOT, T_TOE = 0, 1, 2, 3, 4, 5
T_SPINE, T_NECK, T_HEAD, T_COLLAR, T_SHOULDER, T_ELBOW, T_HAND, T_FINGER, T_THUMB = 6, 7, 8, 9, 10, 11, 12, 13, 14
T_OTHER = 18
# Rename Joints From Labels spells the enum name without spaces, except Foot Thumb
RENAME_TYPE = {i: t.replace(" ", "") for i, t in enumerate(TYPES)}

# Add Joint Labels menu items -> (type value, act on descendants too, also set side Center); "ARM" / "LEG" are the
# first "Label Shoulder" / "Label Hip" items (Maya labels a whole limb from the selected top joint).
LABEL_TYPES = {
    "NONE": (T_NONE, False, True), "ROOT": (T_ROOT, False, True), "HIP": (T_HIP, False, False),
    "KNEE": (T_KNEE, False, False), "FOOT": (T_FOOT, False, False), "TOE": (T_TOE, False, False),
    "SPINE": (T_SPINE, False, True), "NECK": (T_NECK, False, True), "HEAD": (T_HEAD, False, True),
    "COLLAR": (T_COLLAR, False, False), "SHOULDER": (T_SHOULDER, False, False), "ELBOW": (T_ELBOW, False, False),
    "HAND": (T_HAND, False, False), "FINGER": (T_FINGER, False, False), "THUMB": (T_THUMB, True, False),
    "INDEX_FINGER": (19, True, False), "MIDDLE_FINGER": (20, True, False), "RING_FINGER": (21, True, False),
    "PINKY_FINGER": (22, True, False), "EXTRA_FINGER": (23, True, False), "BIG_TOE": (24, True, False),
    "INDEX_TOE": (25, True, False), "MIDDLE_TOE": (26, True, False), "RING_TOE": (27, True, False),
    "PINKY_TOE": (28, True, False), "FOOT_THUMB": (29, True, False),
}
_TYPE_ITEMS = [("KEEP", "(keep)", "Leave the type"),
               ("ARM", "Arm", "Maya's first Label Shoulder item: Shoulder / Elbow / Hand / Finger down the limb"),
               ("LEG", "Leg", "Maya's first Label Hip item: Hip / Knee / Foot / Toe down the limb")]
_TYPE_ITEMS += [(k, TYPES[v[0]], "") for k, v in LABEL_TYPES.items()]
_SIDE_ITEMS = [("KEEP", "(keep)", "Leave the side"), ("LEFT", "Left", ""), ("RIGHT", "Right", ""),
               ("CENTER", "Center", ""), ("NONE", "None", "")]

LIMBS = {"LEG": (T_HIP, T_KNEE, T_FOOT, T_TOE), "ARM": (T_SHOULDER, T_ELBOW, T_HAND, T_FINGER)}


# --- label storage -------------------------------------------------------------------------------------------------

def store(ob, name):
    """Where bone ``name``'s label lives: the edit bone in edit mode, else the data bone (None = no such bone)."""
    if ob.mode == 'EDIT':
        return ob.data.edit_bones.get(name)
    return ob.data.bones.get(name)


def get_label(bone):
    """(side, type, other type, draw label) of a Bone / EditBone, default values (like Maya) where unset."""
    return (int(bone.get(SIDE, CENTER)), int(bone.get(TYPE, T_NONE)), str(bone.get(OTHER, OTHER_DEFAULT)),
            bool(bone.get(DRAW, False)))


def set_label(bone, side=None, type=None, other_type=None, draw=None):
    if side is not None:
        bone[SIDE] = int(side)
    if type is not None:
        bone[TYPE] = int(type)
    if other_type is not None:
        bone[OTHER] = str(other_type)
    if draw is not None:
        bone[DRAW] = bool(draw)


SUFFIX = {CENTER: "", LEFT: " (L)", RIGHT: " (R)", NO_SIDE: " (None)"}


def label_text(bone):
    """The text Maya draws next to a joint with Draw Label on: type (Other: its other type) + side suffix,
    "Hip (L)", "Index Finger (R)", "Knee (None)", "Spine" (Maya)."""
    side, typ, other, _draw = get_label(bone)
    return (other if typ == T_OTHER else TYPES[typ]) + SUFFIX.get(side, "")


# --- which joints --------------------------------------------------------------------------------------------------

def _cb():
    from ..ui import channel_box
    return channel_box


def selected_joints(context):
    """[(armature object, bone name)] the user picked: pose bones / edit bones, else selected skeletons' roots."""
    cb = _cb()
    ob = context.active_object
    if ob is not None and ob.type == 'ARMATURE' and ob.mode == 'EDIT':
        objs = [o for o in getattr(context, "objects_in_mode", None) or [ob] if o.type == 'ARMATURE'] or [ob]
        return [(o, eb.name) for o in objs for eb in o.data.edit_bones if eb.select and not eb.hide]
    if cb.pose_armature(context) is not None:
        return [(pb.id_data, pb.name) for pb in cb.selected_bones(context)]
    out = []
    for o in context.selected_objects:
        if o.type == 'ARMATURE':
            out += [(o, b.name) for b in o.data.bones if b.parent is None]
    return out


def _children(ob, name):
    b = store(ob, name)
    return [c.name for c in b.children] if b is not None else []


def with_descendants(pairs):
    """``cmds.ls(selection=True, dag=True)``: the joints and everything below them, depth first, each once."""
    out, seen = [], set()

    def walk(ob, name):
        key = (ob.name, name)
        if key in seen:
            return
        seen.add(key)
        out.append((ob, name))
        for c in _children(ob, name):
            walk(ob, c)
    for ob, name in pairs:
        walk(ob, name)
    return out


def all_joints(context):
    """``cmds.ls(type="joint")``: every bone of every skeleton in the scene."""
    seen, out = set(), []
    for o in context.scene.objects:
        if o.type == 'ARMATURE' and o.data.name not in seen:
            seen.add(o.data.name)
            names = [eb.name for eb in o.data.edit_bones] if o.mode == 'EDIT' else [b.name for b in o.data.bones]
            out += [(o, n) for n in names]
    return out


# --- Maya rules (pure) -------------------------------------------------------------------------

def _has(name, *words):
    return any(w in name for w in words)


def _has2(name, word):
    """Maya's joint label name match for "word": case-sensitive, lower or capitalised."""
    return word in name or (word[0].upper() + word[1:]) in name


def label_info_for_name(name):
    """(type, side) Maya reads from a joint name; -1 = leave that attribute (Label Based on Joint Names)."""
    typ, side = -1, -1
    m = lambda *ws: any(_has2(name, w) for w in ws)       # noqa: E731
    if m("root", "pelvis", "hips"):
        side, typ = CENTER, T_ROOT
    elif m("hip") or _has(name, "upleg", "UpLeg"):
        typ = T_HIP
    elif m("knee", "leg"):
        typ = T_KNEE
    elif m("back", "spine"):
        side, typ = CENTER, T_SPINE
    elif m("neck"):
        side, typ = CENTER, T_NECK
    elif m("head"):
        side, typ = CENTER, T_HEAD
    elif m("collar"):
        typ = T_COLLAR
    elif m("elbow") or _has(name, "forearm", "ForeArm"):
        typ = T_ELBOW
    elif m("shoulder", "arm"):
        typ = T_SHOULDER
    elif _has(name, "footthumb", "FootThumb"):
        typ = 29
    elif m("thumb"):
        typ = T_THUMB
    elif _has(name, "propa", "PropA"):
        typ = 15
    elif _has(name, "propb", "PropB"):
        typ = 16
    elif _has(name, "propc", "PropC"):
        typ = 17
    elif m("other"):
        typ = T_OTHER
    else:
        hand = m("finger", "hand")
        toe = m("toe", "foot")
        for word, finger_type in (("index", 19), ("middle", 20), ("ring", 21), ("pinky", 22)):
            if m(word) and hand:
                typ = finger_type
                break
        else:
            if m("extra") and not m("foot") and hand:
                typ = 23
            elif _has(name, "bigtoe", "BigToe"):
                typ = 24
            else:
                for word, toe_type in (("index", 25), ("middle", 26), ("ring", 27), ("pinky", 28), ("extra", 29)):
                    if m(word) and toe:
                        typ = toe_type
                        break
                else:
                    if m("finger"):
                        typ = T_FINGER
                    elif m("toe"):
                        typ = T_TOE
                    elif m("foot"):
                        typ = T_FOOT
                    elif m("hand"):
                        typ = T_HAND
    if m("left"):
        side = LEFT
    elif m("right"):
        side = RIGHT
    elif m("center"):
        side = CENTER
    if side == -1 and name[:1] in ("l", "L"):
        side = LEFT
    elif side == -1 and name[:1] in ("r", "R"):
        side = RIGHT
    return typ, side


def name_from_label(side, typ):
    """Rename Joints From Labels: side + type name, or None when the side or the type is None (no rename)."""
    if side == NO_SIDE or typ == T_NONE:
        return None
    return SIDES[side] + RENAME_TYPE[typ]


def _roll(name):
    return "Roll" in name or "roll" in name


def limb_labels(limb, chain):
    """Types Maya's Label Shoulder (ARM) / Label Hip (LEG) item gives ``chain`` = [(name, joint children)], the
    selected top joint first, then every joint below it depth first."""
    top, mid, end, digit = LIMBS[limb]
    out = [top]
    cur = top
    for name, kids in chain[1:]:
        if limb == "LEG":
            if not _roll(name) and cur != digit:
                cur += 1
        else:
            if not _roll(name):
                if cur == mid:
                    if kids > 1 or _has2(name, "hand") or _has2(name, "wrist"):
                        cur += 1
                elif cur != digit:
                    cur += 1
        out.append(cur)
    if limb == "ARM":
        n = len(chain)
        if n == 3:
            out[2] = end
        elif n > 3:
            on_elbow = True
            for i in range(2, n):
                if on_elbow:
                    if "lbow" not in chain[i][0]:
                        on_elbow = False
                        out[i] = end
                else:
                    out[i] = digit
    return out


# --- operators -----------------------------------------------------------------------------------------------------

def _labels(pairs):
    return [(ob, name, store(ob, name)) for ob, name in pairs if store(ob, name) is not None]


def _redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _tag(pairs):
    for ob in {ob for ob, _n in pairs}:
        ob.data.update_tag()


class ALLSET_OT_joint_label(bpy.types.Operator):
    """Maya Skeleton > Joint Labelling > Add Joint Labels: set the side or the type label of the selected joints"""
    bl_idname = "allset.joint_label"
    bl_label = "Add Joint Label"
    bl_options = {'REGISTER', 'UNDO'}

    side: EnumProperty(name="Side", items=_SIDE_ITEMS, default="KEEP", options={'SKIP_SAVE'})
    type: EnumProperty(name="Type", items=_TYPE_ITEMS, default="KEEP", options={'SKIP_SAVE'})

    def execute(self, context):
        sel = selected_joints(context)
        if not sel:
            self.report({'ERROR'}, "Select joints to label.")
            return {'CANCELLED'}
        if self.side != "KEEP":
            value = SIDES.index(self.side.title())
            # Maya Label Center / Left / Right / None: Center on the selected joints only, Left / Right / None also
            # below them
            for _ob, _n, b in _labels(sel if value == CENTER else with_descendants(sel)):
                set_label(b, side=value)
        if self.type in LIMBS:
            for ob, name in sel:
                chain = with_descendants([(ob, name)])
                types = limb_labels(self.type, [(n, len(_children(o, n))) for o, n in chain])
                for (o, n), t in zip(chain, types):
                    set_label(store(o, n), type=t)
        elif self.type != "KEEP":
            value, dag, center = LABEL_TYPES[self.type]
            if center:
                for _ob, _n, b in _labels(sel):
                    set_label(b, side=CENTER)
            for _ob, _n, b in _labels(with_descendants(sel) if dag else sel):
                set_label(b, type=value)
        _tag(sel)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_joint_label_toggle(bpy.types.Operator):
    """Maya Toggle Selected Labels: show or hide the labels of the selected joints and the joints below them"""
    bl_idname = "allset.joint_label_toggle"
    bl_label = "Toggle Selected Labels"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        joints = _labels(with_descendants(selected_joints(context)))
        if not joints:
            self.report({'ERROR'}, "No joints selected.")
            return {'CANCELLED'}
        on = not get_label(joints[0][2])[3]           # Maya: the first joint decides
        for _ob, _n, b in joints:
            set_label(b, draw=on)
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_joint_label_show_all(bpy.types.Operator):
    """Maya Show All Labels / Hide All Labels: every joint in the scene"""
    bl_idname = "allset.joint_label_show_all"
    bl_label = "Show All Labels"
    bl_options = {'REGISTER', 'UNDO'}

    show: BoolProperty(name="Show", default=True, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return ("Show the labels of every joint in the scene" if properties.show
                else "Hide the labels of every joint in the scene")

    def execute(self, context):
        for _ob, _n, b in _labels(all_joints(context)):
            set_label(b, draw=self.show)
        _redraw(context)
        return {'FINISHED'}


def unique_bone_name(ob, want, current):
    """``want``, or Maya's clash rule ``want1``, ``want2`` ... when another bone of this skeleton has it."""
    names = {b.name for b in (ob.data.edit_bones if ob.mode == 'EDIT' else ob.data.bones)} - {current}
    if want not in names:
        return want
    n = 1
    while f"{want}{n}" in names:
        n += 1
    return f"{want}{n}"


class ALLSET_OT_rename_joints_from_labels(bpy.types.Operator):
    """Maya Rename Joints From Labels: name the selected joints and the joints below them side + type
    (LeftHip); joints whose side or type is None keep their name"""
    bl_idname = "allset.rename_joints_from_labels"
    bl_label = "Rename Joints From Labels"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        joints = with_descendants(selected_joints(context))
        if not joints:
            self.report({'ERROR'}, "Select joints to rename.")
            return {'CANCELLED'}
        n = 0
        for ob, name in reversed(joints):               # Maya renames from the last joint up
            b = store(ob, name)
            if b is None:
                continue
            side, typ, _o, _d = get_label(b)
            want = name_from_label(side, typ)
            if want is None:
                continue
            b.name = unique_bone_name(ob, want, b.name)  # Blender renames vertex groups / constraint targets too
            n += 1
        _redraw(context)
        return {'FINISHED'}


class ALLSET_OT_label_from_joint_names(bpy.types.Operator):
    """Maya Label Based on Joint Names: read side and type labels from the names of the selected joints and the
    joints below them (L_arm = Left Shoulder)"""
    bl_idname = "allset.label_from_joint_names"
    bl_label = "Label Based on Joint Names"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        joints = _labels(with_descendants(selected_joints(context)))
        if not joints:
            self.report({'ERROR'}, "Select joints to label.")
            return {'CANCELLED'}
        for _ob, name, b in joints:
            typ, side = label_info_for_name(name)
            set_label(b, type=typ if typ != -1 else None, side=side if side != -1 else None)
        _redraw(context)
        return {'FINISHED'}


# --- Enable / Disable Selected IK Handles --------------------------------------------------------------------------

def selected_ik_constraints(context):
    """IK / Spline IK constraints of the selected IK handles: handle empties (the kit's ``ikHandleN`` targets) and,
    in pose mode, selected bones that carry a kit IK (a Spline IK handle has no object of its own)."""
    from .skin import ik_constraints_on
    out = []
    for o in context.selected_objects:
        out += [con for _a, _pb, con in ik_constraints_on(o)]
    cb = _cb()
    if cb.pose_armature(context) is not None:
        for pb in cb.selected_bones(context):
            out += [c for c in pb.constraints if c.type in {'IK', 'SPLINE_IK'}]
    seen, uniq = set(), []
    for con in out:
        if con.as_pointer() not in seen:
            seen.add(con.as_pointer())
            uniq.append(con)
    return uniq


class ALLSET_OT_ik_handle_enable(bpy.types.Operator):
    """Maya Enable / Disable Selected IK Handles: turn the selected IK handles' IK on (Ik Blend 1) or off
    (Ik Blend 0 = the joints follow their own rotation)"""
    bl_idname = "allset.ik_handle_enable"
    bl_label = "Enable Selected IK Handles"
    bl_options = {'REGISTER', 'UNDO'}

    enable: BoolProperty(name="Enable", default=True, options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return ("Turn the IK of the selected IK handles on" if properties.enable
                else "Turn the IK of the selected IK handles off (the joints keep their FK rotation)")

    def execute(self, context):
        cons = selected_ik_constraints(context)
        if not cons:
            self.report({'ERROR'}, "No handle selected.")       # Maya ikHandle -e -eh / -dh with no handle
            return {'CANCELLED'}
        from . import ik_fk
        for con in cons:
            # Maya ikHandle -eh / -dh write ikBlend 1 / 0; Ik Blend drives the Influence
            pb = next((p for p in con.id_data.pose.bones if any(c == con for c in p.constraints)), None)
            if con.type == 'IK' and pb is not None:
                ik_fk.set_blend(con.id_data, pb, con, 1.0 if self.enable else 0.0)
            else:
                con.influence = 1.0 if self.enable else 0.0
            con.id_data.update_tag()
        context.view_layer.update()
        return {'FINISHED'}


classes = (ALLSET_OT_joint_label, ALLSET_OT_joint_label_toggle, ALLSET_OT_joint_label_show_all,
           ALLSET_OT_rename_joints_from_labels, ALLSET_OT_label_from_joint_names, ALLSET_OT_ik_handle_enable)


# --- viewport label drawing ----------------------------------------------------------------------------------------

# Maya 2022 label look: colour by side; Left text starts at the joint, Right text ends at
# it, Center / None text is centred over it; the text sits just above the joint.
def _srgb(h):
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)


SIDE_COLORS = {CENTER: _srgb("2e0f46"), LEFT: _srgb("747bca"), RIGHT: _srgb("8ec28d"), NO_SIDE: _srgb("a70009")}
LABEL_RISE = 10                # px above the joint at UI scale 1.0
LABEL_SIZE = 11                # font px at UI scale 1.0
_handles = []


_armature_cache = {}


def _armatures(view_layer):
    """The view layer's armature objects, kept until the scene's structure changes (#191: every 3D View
    redraw walked every object)."""
    from ..ui.outliner import structure_version
    key = (structure_version(), len(view_layer.objects))
    got = _armature_cache.get(view_layer.as_pointer())
    if got is None or got[0] != key:
        got = (key, [ob.name for ob in view_layer.objects if ob is not None and ob.type == 'ARMATURE'])
        _armature_cache[view_layer.as_pointer()] = got
    objects = view_layer.objects
    return [objects[n] for n in got[1] if n in objects]


def label_points(context):
    """[(world point, text, side)] for every visible joint with Draw Label on."""
    out = []
    for ob in _armatures(context.view_layer):
        if ob is None or not ob.visible_get():
            continue
        mw = ob.matrix_world
        if ob.mode == 'EDIT':
            bones = [(eb, eb.head) for eb in ob.data.edit_bones if not eb.hide and eb.get(DRAW)]
        elif ob.pose is not None:
            bones = [(pb.bone, pb.head) for pb in ob.pose.bones if pb.bone.get(DRAW) and not pb.bone.hide]
        else:
            bones = [(b, b.head_local) for b in ob.data.bones if b.get(DRAW) and not b.hide]
        out += [(mw @ head, label_text(b), get_label(b)[0]) for b, head in bones]
    return out


def draw_labels():
    context = bpy.context
    space, region, rv3d = context.space_data, context.region, context.region_data
    if space is None or rv3d is None or not getattr(space, "show_object_viewport_armature", True):
        return                                   # the Tool Box column hides armatures
    pts = label_points(context)
    if not pts:
        return
    scale = context.preferences.system.ui_scale or 1.0
    font = 0
    blf.size(font, round(LABEL_SIZE * scale))
    gpu.state.blend_set('ALPHA')
    for p, text, side in pts:
        xy = view3d_utils.location_3d_to_region_2d(region, rv3d, p)
        if xy is None:
            continue
        w = blf.dimensions(font, text)[0]
        x = xy.x if side == LEFT else xy.x - w if side == RIGHT else xy.x - w / 2
        blf.color(font, *SIDE_COLORS.get(side, SIDE_COLORS[CENTER]))
        blf.position(font, round(x), round(xy.y + LABEL_RISE * scale), 0)
        blf.draw(font, text)
    gpu.state.blend_set('NONE')


def register_bindings():
    if not _handles:
        _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw_labels, (), 'WINDOW', 'POST_PIXEL'))


def unregister_bindings():
    while _handles:
        bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), 'WINDOW')
