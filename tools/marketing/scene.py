"""Scene helpers shared by tools/marketing/shots.py (stills) and tools/marketing/clips.py (clips).

Runs inside a GUI Blender started with --enable-event-simulate (tests/gui/sim.py). The scene is built from the
licensed models in the local assets folder (tools/marketing/assets.json, docs/distribution/marketing/CREDITS.md):
Blender Studio's Rain, Pack Bot and Security Bot rigs, the Blender 4.5 splash scene DOGWALK, Cube Diorama props and
the Poly Haven Studio Small 09 HDRI (local asset inventory).

Viewport background (#41): the kit ships no theme (#40),
so these captures use Blender's factory theme and never write one (``theme_unchanged`` is checked with every capture).
The Maya layout viewport is flat grey #5c5c5c, which without a theme is view / scene
data: Solid views get the view's own background colour (``View3DShading.background_type = 'VIEWPORT'``, what the
Maya layout template saves, #45). Material Preview ignores that colour (it draws the theme background), so
in Maya mode it uses the scene world ``.Allset Marketing World`` = the Studio Small 09 HDRI for lighting and flat
#5c5c5c for camera rays (Light Path "Is Camera Ray"; #5c5c5c with Standard, #5a5a5a with AgX = dE00 < 1).
``maya_look()`` turns it on and a persistent timer (``LOOK_KEEPER``) keeps every 3D View of every window in that state,
so views made later in a session (Graph Editor split, switch back from Blender, new windows) are flat Maya grey
before they are drawn; captures are checked afterwards by tools/marketing/bg_check.py (``viewport_rects`` = what to
check). Plain Blender (Blender mode) keeps Blender's own background: the keeper puts Material Preview views back on
the HDRI studio light with background alpha 0 (the factory theme shows).
"""

import math
import sys
from importlib import import_module
from pathlib import Path

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Euler, Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))      # bg_check.py
sys.path.insert(0, str(ROOT / "tests" / "gui"))
from sim import MODULE, view3d, win  # noqa: E402

ASSETS = ROOT / "research" / "marketing_assets"


def mod(name):
    return import_module(MODULE + name)


def prefs():
    return bpy.context.preferences.addons[MODULE].preferences


def redraw():
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            a.tag_redraw()


def v3d_override():
    area, region = view3d()
    return bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region)


def area_rect(a):
    h = win().height
    return [a.x, h - (a.y + a.height), a.width, a.height]


def region_rect(r):
    h = win().height
    return [r.x, h - (r.y + r.height), r.width, r.height]


def screen_pos(ob, local=(0, 0, 0), world=None):
    """Window pixel (bottom-up, as event_simulate wants) of a point of ``ob`` (or of ``world``) in the main view."""
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    p = Vector(world) if world is not None else ob.matrix_world @ Vector(local)
    co = location_3d_to_region_2d(region, rv3d, p)
    return int(region.x + co.x), int(region.y + co.y)


def to_top(x, y):
    return [x, win().height - y]


def select(obs, active=None):
    with v3d_override():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    for o in bpy.context.view_layer.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = active or (obs[-1] if obs else None)


def bounds(objs):
    """World bounding box of the visible meshes of ``objs`` (evaluated: modifiers / GN / armature pose included)."""
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type not in {'MESH', 'CURVE'} or not o.visible_get():
            continue
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def frame(obs, zoom=1.0, rot=None, offset=(0, 0, 0)):
    """Frame objects in the main view (Maya F), then move the camera back by ``zoom``; ``offset`` moves the centre
    (world units)."""
    area, region = view3d()
    rv3d = area.spaces.active.region_3d
    if rot is not None:
        rv3d.view_rotation = Euler([math.radians(a) for a in rot]).to_quaternion()
    rv3d.view_perspective = 'PERSP'
    lo, hi = bounds(obs)
    rv3d.view_location = (lo + hi) / 2 + Vector(offset)
    rv3d.view_distance = (hi - lo).length * 1.25 * zoom


def look(location, rot, distance):
    """Set the main view: centre ``location``, Euler ``rot`` (degrees), ``distance``."""
    area, _region = view3d()
    rv3d = area.spaces.active.region_3d
    rv3d.view_perspective = 'PERSP'
    rv3d.view_rotation = Euler([math.radians(a) for a in rot]).to_quaternion()
    rv3d.view_location = Vector(location)
    rv3d.view_distance = distance


# ------------------------------------------------------------------------------------------------------ assets
# Blender Studio / blender.org files (tools/marketing/assets.json, local asset inventory,
# docs/distribution/marketing/CREDITS.md). Collections are appended at scale 1 (the files are metric, the template is
# metres with cm display); the files' own cameras / lights are not used; widget / helper collections stay hidden.
# Python auto-exec stays off (factory default): CloudRig's UI scripts don't run, the rigs still pose.
FILES = {
    "rain": ASSETS / "bs_rain_v3" / "Rain v3.3" / "rain_v3.2.blend",
    "pack": ASSETS / "bs_pack_bot" / "pack_bot_v1" / "pack_bot_release_v1.blend",
    "sec": ASSETS / "bs_security_bot" / "security_bot_v1" / "security_bot_release_v1.blend",
    "dog": ASSETS / "bdemo_splash_45" / "blender-4.5-splash.blend",
    "cube": ASSETS / "bdemo_cube_diorama" / "cube_diorama" / "cube_diorama.blend",
}
HDRI = ASSETS / "ph_studio_small_09" / "studio_small_09_2k.hdr"
HIDDEN_COLLECTION_WORDS = ("widgets", "helpers", "WGT", "splats", "droplets", "boolean_diff", "curve_deformers",
                           "rigging-", "leash_points", "collision")
RAIN_BONES = {"Main Controls", "IK Controls", "FK Controls", "Fingers", "Face Main"}


def _layer_collection(lc, col):
    if lc.collection == col:
        return lc
    for ch in lc.children:
        r = _layer_collection(ch, col)
        if r is not None:
            return r
    return None


def append(key, names):
    """Append collections ``names`` of FILES[key] and link them to the scene. Hidden: widget / helper collections;
    removed: the file's cameras and lights. Returns the visible objects."""
    out = []
    for col in append_cols(key, names):
        out += list(col.all_objects)
    return [o for o in out if o.name in bpy.context.view_layer.objects and o.visible_get()]


def append_cols(key, names):
    """``append`` returning the appended collections (names may get .001 when a collection came in before)."""
    with bpy.data.libraries.load(str(FILES[key]), link=False) as (src, dst):
        missing = [n for n in names if n not in src.collections]
        assert not missing, f"{key}: no collection {missing}"
        dst.collections = list(names)
    sc = bpy.context.scene
    for col in dst.collections:
        sc.collection.children.link(col)
        for o in list(col.all_objects):
            if o.type in {'CAMERA', 'LIGHT', 'LIGHT_PROBE'}:
                bpy.data.objects.remove(o)
        for sub in col.children_recursive:
            if any(w in sub.name for w in HIDDEN_COLLECTION_WORDS):
                lc = _layer_collection(bpy.context.view_layer.layer_collection, sub)
                if lc is not None:
                    lc.exclude = True
    bpy.context.view_layer.update()
    return list(dst.collections)


def obj(name):
    return bpy.data.objects[name]


def rain_bone_view(rig):
    """Rain's animator controls only (Main / IK / FK / Fingers / Face Main bone collections and their sub-collections
    that are on in the file); mechanism, deform and helper collections hidden."""
    for c in rig.data.collections_all:
        keep, p = c.name in RAIN_BONES, c.parent
        while p is not None and not keep:
            keep = p.name in RAIN_BONES
            p = p.parent
        c.is_visible = keep and (c.name in RAIN_BONES or c.is_visible)


def pose_bone_world(rig, name, delta):
    """Move a pose bone by ``delta`` (world, metres) — e.g. Rain's IK hand controls out of the T-pose."""
    pb = rig.pose.bones[name]
    m = pb.matrix.copy()
    m.translation += rig.matrix_world.inverted().to_3x3() @ Vector(delta)
    pb.matrix = m
    bpy.context.view_layer.update()


def rain_relaxed(rig):
    """Arms down from the rest T-pose (the IK hand controls, poles stay): the pose Rain is shown in."""
    for side, sx in (("L", 1), ("R", -1)):
        pose_bone_world(rig, f"IK-Hand_Parent.{side}", (RAIN_RELAXED[0] * sx, RAIN_RELAXED[1], RAIN_RELAXED[2]))


def load_rain(relaxed=True):
    objs = append("rain", ["CH-rain"])
    rig = obj("RIG-rain")
    rain_bone_view(rig)
    if relaxed:
        rain_relaxed(rig)
    meshes = [o for o in objs if o.type == 'MESH' and o.name.startswith("GEO-rain")]
    return rig, meshes


def load_pack_bot():
    objs = append("pack", ["CH-pack_bot"])
    return obj("RIG-pack_bot"), [o for o in objs if o.type in {'MESH', 'CURVE'}]


def load_security_bot():
    objs = append("sec", ["CH-security_bot"])
    # its gun arm carries a hidden instance of the battery prop: drop it, so load_battery's parts keep their names
    bat = bpy.data.collections.get("PR-battery")
    if bat is not None:
        for o in list(bat.all_objects) + [o for o in bpy.data.objects if o.instance_collection == bat]:
            bpy.data.objects.remove(o)
        for c in list(bat.children_recursive) + [bat]:
            bpy.data.collections.remove(c)
        bpy.data.orphans_purge(do_local_ids=True, do_recursive=True)
    vl = bpy.context.view_layer.objects
    used = {getattr(m, "object", None) for o in bpy.data.objects for m in getattr(o, "modifiers", [])}
    for o in list(bpy.data.objects):          # hidden parts (gun arm, paint proxies): not part of these shots
        if o.name in vl and (o.hide_get() or o.hide_viewport) and o.type != 'ARMATURE' and o not in used                 and not o.children:
            bpy.data.objects.remove(o)
    objs = [o for o in objs if o.name in bpy.data.objects]
    return obj("RIG-security_bot"), [o for o in objs if o.type in {'MESH', 'CURVE'}]


def load_battery(pos=(0, 0, 0), rot_z=0.0):
    """Security Bot's battery as one prop: every part re-parented (transform kept) to the casing, the 2-bone prop rig
    and its widgets removed, the casing's origin at its bottom centre. Returns (casing, parts)."""
    top = append_cols("sec", ["PR-battery"])[0]
    for c in [top] + list(top.children_recursive):
        if not any(w in c.name for w in HIDDEN_COLLECTION_WORDS):
            c.hide_viewport = False                  # the prop is a hidden instance source in the robot file
    objs = [o for o in top.all_objects]
    for o in objs:
        if not o.name.startswith("WGT-"):
            o.hide_viewport = False
            o.hide_set(False)
    bpy.context.view_layer.update()
    rig = next(o for o in objs if o.type == 'ARMATURE')
    casing = next(o for o in objs if o.name.startswith("GEO-casing_main"))
    parts = [o for o in objs if o.type in {'MESH', 'CURVE'} and o.parent == rig]
    mws = {o: o.matrix_world.copy() for o in parts}
    for o in parts:
        o.parent = None
        o.matrix_world = mws[o]
    for o in [rig] + [o for o in bpy.data.objects if o.name.startswith("WGT-") and o.users_collection
                      and any("battery" in c.name for c in o.users_collection)]:
        bpy.data.objects.remove(o)
    bpy.context.view_layer.update()
    lo, hi = bounds([casing])
    origin_to(casing, ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for o in parts:
        if o is casing:
            continue
        mw = o.matrix_world.copy()
        o.parent = casing
        o.matrix_parent_inverse = casing.matrix_world.inverted()
        o.matrix_world = mw
    casing.location = Vector(pos)
    casing.rotation_euler.z = math.radians(rot_z)
    bpy.context.view_layer.update()
    return casing, parts


def origin_to(ob, world):
    """Move ``ob``'s origin to ``world`` without moving its geometry (children kept where they are)."""
    from mathutils import Matrix
    kids = {c: c.matrix_world.copy() for c in ob.children}
    local = ob.matrix_world.inverted() @ Vector(world)
    ob.data.transform(Matrix.Translation(-local))
    ob.matrix_world = ob.matrix_world @ Matrix.Translation(local)
    bpy.context.view_layer.update()
    for c, mw in kids.items():
        c.matrix_world = mw
    bpy.context.view_layer.update()


def load_cube_props(names):
    """Cube Diorama props (CC0; never "Computer") as standalone objects. Returns {name: object}."""
    assert "Computer" not in names
    with bpy.data.libraries.load(str(FILES["cube"]), link=False) as (src, dst):
        dst.objects = [n for n in names if n in src.objects]
    out = {}
    for o in dst.objects:
        bpy.context.scene.collection.objects.link(o)
        o.parent = None
        out[o.name] = o
    bpy.context.view_layer.update()
    return out


def stand(ob, pos, rot_z=None, objs=None):
    """Put ``ob`` (and what follows it) so the bottom of ``objs`` (default [ob]) sits at ``pos``."""
    bpy.context.view_layer.update()
    lo, hi = bounds(objs or [ob])
    c = (lo + hi) / 2
    if rot_z is not None:
        ob.rotation_euler.z = math.radians(rot_z)
        bpy.context.view_layer.update()
        lo, hi = bounds(objs or [ob])
        c = (lo + hi) / 2
    ob.location += Vector((pos[0] - c.x, pos[1] - c.y, pos[2] - lo.z))
    bpy.context.view_layer.update()


def load_dogwalk(frame_no=85):
    """The Blender 4.5 splash scene: environment, props and characters (its cameras and lights are not used)."""
    objs = append("dog", ["Background", "Props", "Characters"])
    vl = bpy.context.view_layer.objects
    for o in bpy.data.objects:
        if o.name.startswith("LGT-") and o.name in vl:
            o.hide_set(True)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, 120
    sc.frame_set(frame_no)
    return objs


# ------------------------------------------------------------------------------------------------ scenes per feature
def largest_mesh(objs):
    meshes = [o for o in objs if o.type == 'MESH' and o.visible_get()]
    return max(meshes, key=lambda o: len(o.data.vertices)) if meshes else None


def dog_scene(C):
    """First screen / key visual / hotbox / navigation / switch: the DOGWALK splash set (Pinda, Chocomel, snowman)."""
    objs = load_dogwalk()
    vl = bpy.context.view_layer.objects
    for o in bpy.data.objects:
        helper = o.type == 'LATTICE' or o.name.startswith(("COL-", "LGT-", "WGT-")) or "leash" in o.name.lower()
        if helper:
            o.hide_viewport = True               # also inside the collection instances (trees, bushes)
            if o.name in vl:
                o.hide_set(True)
        elif o.type == 'EMPTY':
            o.empty_display_size = 1e-4          # collection-instance empties: no axes drawn
    def member(colname):
        col = bpy.data.collections.get(colname)
        return [o for o in col.all_objects] if col else []
    C["dog_objs"] = [o for o in objs if o.visible_get()]
    C["snowman"] = next((o for o in member("PR-snowman") if "body" in o.name and o.type == 'MESH'), None) \
        or largest_mesh(member("PR-snowman"))
    C["snow_head"] = next((o for o in member("PR-snowman") if "head" in o.name and o.type == 'MESH'), C["snowman"])
    C["pinda"] = largest_mesh(member("CH-Pinda"))
    C["chocomel"] = largest_mesh(member("CH-Chocomel"))
    C["dog_chars"] = [o for o in member("CH-Pinda") + member("CH-Chocomel") + member("PR-snowman")
                      if o.type == 'MESH' and o.visible_get()]
    return all(C[k] for k in ("snowman", "pinda", "chocomel"))


def dog_view(kind="hero"):
    """Hand-framed views of the DOGWALK set (world metres; the characters stand around x -2 .. 1.3, y -2 .. 0.8)."""
    views = {
        "hero": ((-0.55, -0.6, 0.8), (87, 0, -8), 5.4),     # horizon ~40 % down: Maya's grey above it
        "hotbox": ((-0.5, -0.5, 0.85), (87, 0, -14), 6.2),
        "wide": ((-0.5, -0.3, 0.9), (87, 0, -22), 8.0),
    }
    look(*views[kind])


def lab_scene(C):
    """Pivot / snapping / mechanical Channel Box: Security Bot, a display-case pedestal (Cube Diorama) and the
    battery prop on it."""
    rig, objs = load_security_bot()
    props = load_cube_props(["Display Case"])
    case = props["Display Case"]
    stand(case, (0.62, -0.55, 0.0), rot_z=-20)
    top = bounds([case])[1].z
    casing, parts = load_battery()
    stand(casing, (0.62, -0.55, top), objs=[casing] + parts)
    casing.rotation_euler.z = math.radians(-25)
    bpy.context.view_layer.update()
    C.update(sec_rig=rig, sec_objs=objs, case=case, battery=casing, battery_parts=parts, case_top=top)
    return True


def pack_scene(C):
    """Modeling Toolkit / components: Pack Bot."""
    rig, objs = load_pack_bot()
    objs = [o for o in objs if o.type == 'MESH' and o.name.startswith("GEO")]   # no path / cable helper curves
    C.update(pack_rig=rig, pack_objs=objs, torso=obj("GEO-shell_torso"))
    return True


RAIN_RELAXED = (-0.30, -0.05, -0.50)        # IK hand controls from the T-pose (world m, mirrored for .R)


def rain_scene(C, relaxed=True):
    """Rigging / skin weights / animation / marking menus: Rain, arms relaxed."""
    rig, meshes = load_rain(relaxed=relaxed)
    C.update(rig=rig, rain_meshes=meshes, top_mesh=obj("GEO-rain-top"), body=obj("GEO-rain-body"),
             jeans=obj("GEO-rain-jeans"))
    return True


def rain_keys(rig, frames=(1, 12, 24)):
    """A small wave on Rain: right IK hand up and back, hips dip, keyed on the pose bones (Graph Editor curves)."""
    sc = bpy.context.scene
    hand, hips = rig.pose.bones["IK-Hand_Parent.R"], rig.pose.bones["MSTR-Hips"]
    base_h, base_p = hand.location.copy(), hips.location.copy()
    poses = {frames[0]: ((0, 0, 0), 0.0), frames[1]: ((0.10, -0.12, 0.62), -0.035), frames[2]: ((0, 0, 0), 0.0)}
    for f, (dh, dz) in poses.items():
        sc.frame_set(f)
        hand.location = base_h
        hips.location = base_p
        bpy.context.view_layer.update()
        if any(dh):
            pose_bone_world(rig, "IK-Hand_Parent.R", dh)
        pose_bone_world(rig, "MSTR-Hips", (0, 0, dz))
        hand.keyframe_insert("location", frame=f)
        hips.keyframe_insert("location", frame=f)
    for f in (6, 18):
        sc.frame_set(f)
        bpy.context.view_layer.update()
        hips.keyframe_insert("location", frame=f)
    sc.frame_start, sc.frame_end = 1, 24
    sc.frame_set(8)


# ------------------------------------------------------------------------------------------------ look-dev
LOOK = {"rotate": 0.0, "intensity": 1.0}
WORLD_NAME = ".Allset Marketing World"
FLAT_SRGB = 0.36            # flat viewport grey #5c5c5c (operators/key_batch3.FLAT)


def studio_light():
    """The Poly Haven Studio Small 09 HDRI as a Material Preview studio light (Blender-mode views; sandbox prefs)."""
    lights = bpy.context.preferences.studio_lights
    name = HDRI.name
    sl = next((s for s in lights if s.name == name), None)
    if sl is None:
        sl = lights.load(str(HDRI), 'WORLD')
    return sl.name


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def marketing_world():
    """The scene world of Maya-mode Material Preview views: the HDRI lights the scene, camera rays see flat Maya
    grey (Light Path "Is Camera Ray"), so the viewport background is #5c5c5c without a theme."""
    w = bpy.data.worlds.get(WORLD_NAME)
    if w is None:
        w = bpy.data.worlds.new(WORLD_NAME)
        w.use_fake_user = True
        w.use_nodes = True
        nt = w.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputWorld")
        coord = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.name = "rotate"
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(str(HDRI), check_existing=True)
        light = nt.nodes.new("ShaderNodeBackground")
        light.name = "light"
        flat = nt.nodes.new("ShaderNodeBackground")
        flat.inputs[0].default_value = (_lin(FLAT_SRGB),) * 3 + (1.0,)
        path = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs[0], env.inputs[0])
        nt.links.new(env.outputs[0], light.inputs[0])
        nt.links.new(path.outputs["Is Camera Ray"], mix.inputs[0])
        nt.links.new(light.outputs[0], mix.inputs[1])
        nt.links.new(flat.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs[0])
    nt = w.node_tree
    rot = nt.nodes["rotate"].inputs["Rotation"]
    want = (0.0, 0.0, math.radians(LOOK["rotate"]))
    if any(abs(a - b) > 1e-5 for a, b in zip(rot.default_value, want)):
        rot.default_value = want
    strength = nt.nodes["light"].inputs["Strength"]
    if abs(strength.default_value - LOOK["intensity"]) > 1e-6:
        strength.default_value = LOOK["intensity"]
    sc = bpy.context.scene
    if sc.world is not w:
        sc.world = w
    return w


def _material_maya(sh):
    """A Material Preview view in the Maya look: the marketing world (flat grey to the camera, HDRI light)."""
    changed = False
    if not sh.use_scene_world:
        sh.use_scene_world = True
        changed = True
    if sh.use_scene_lights:
        sh.use_scene_lights = False
        changed = True
    return changed


def _material_blender(sh, name):
    """A Material Preview view in plain Blender: the HDRI studio light over Blender's own (theme) background."""
    changed = False
    if sh.use_scene_world:
        sh.use_scene_world = False
        changed = True
    if sh.use_scene_lights:
        sh.use_scene_lights = False
        changed = True
    if sh.studio_light != name:
        sh.studio_light = name
        changed = True
    rz = math.radians(LOOK["rotate"])
    if abs(sh.studiolight_rotate_z - rz) > 1e-5:
        sh.studiolight_rotate_z = rz
        changed = True
    if abs(sh.studiolight_intensity - LOOK["intensity"]) > 1e-5:
        sh.studiolight_intensity = LOOK["intensity"]
        changed = True
    if sh.studiolight_background_alpha != 0.0:
        sh.studiolight_background_alpha = 0.0
        sh.studiolight_background_blur = 0.0
        changed = True
    return changed


def _solid_maya(sh):
    """A Solid / Wireframe view in the Maya look: its own flat #5c5c5c (view data, like the Maya layout views)."""
    if sh.background_type == 'VIEWPORT' and all(abs(c - _lin(FLAT_SRGB)) < 1e-4 for c in sh.background_color):
        return False
    mod(".operators.key_batch3").set_shading(sh, "GREY")
    return True


def shading(kind='MATERIAL', rotate=0.0, intensity=1.0, clip_end=None):
    """Material Preview lit by the HDRI in every 3D View but the Tool Box column (Maya mode: over flat Maya grey,
    see the module docstring); ``kind`` 'SOLID' = studio-lit solid with material colours."""
    LOOK["rotate"], LOOK["intensity"] = rotate, intensity
    maya = maya_mode_on()
    name = studio_light() if kind == 'MATERIAL' and not maya else None
    if kind == 'MATERIAL' and maya:
        marketing_world()
    for a in win().screen.areas:
        if a.type == 'VIEW_3D' and not mod(".ui.toolbox").is_toolbox(a.spaces.active):
            sp = a.spaces.active
            sh = sp.shading
            sh.type = kind
            if kind == 'MATERIAL':
                if maya:
                    _material_maya(sh)
                else:
                    _material_blender(sh, name)
            else:
                sh.light = 'STUDIO'
                sh.color_type = 'MATERIAL'
                sh.show_cavity = True
                if maya:
                    _solid_maya(sh)
            ov = sp.overlay
            ov.show_floor = True
            ov.show_bones = False                    # bones only in the rigging shots
            ov.show_relationship_lines = False
            if hasattr(sp, "show_region_asset_shelf"):
                sp.show_region_asset_shelf = False
            if clip_end:
                sp.clip_end = clip_end


def show_bones(on):
    for a in win().screen.areas:
        if a.type == 'VIEW_3D':
            a.spaces.active.overlay.show_bones = on


# ------------------------------------------------------------------------------------------------ Maya look
LOOK_STATE = {"on": False, "theme": None}
KEEPER_INTERVAL = 0.05      # s: well inside one recording tick (0.3 - 0.7 s), so a new view is flat grey when drawn


def maya_mode_on():
    try:
        return mod(".switch").is_on()
    except Exception:
        return False


def theme_signature():
    """A hash of every value of the active theme (Blender's factory theme in the sandbox): the captures must never
    write a theme (#40, #41)."""
    import hashlib
    out = []

    def walk(struct, prefix, depth):
        for prop in struct.bl_rna.properties:
            ident = prop.identifier
            if ident == "rna_type" or depth > 6:
                continue
            value = getattr(struct, ident)
            if prop.type == 'POINTER':
                if value is not None:
                    walk(value, f"{prefix}{ident}.", depth + 1)
            elif prop.type == 'COLLECTION':
                for i, item in enumerate(value):
                    walk(item, f"{prefix}{ident}[{i}].", depth + 1)
            else:
                try:
                    value = tuple(value)
                except TypeError:
                    pass
                out.append((prefix + ident, repr(value)))
    walk(bpy.context.preferences.themes[0], "", 0)
    return hashlib.sha1(repr(sorted(out)).encode()).hexdigest()


def theme_unchanged():
    """True while the theme is the one ``maya_look()`` found (nothing wrote a theme since)."""
    return LOOK_STATE["theme"] is None or theme_signature() == LOOK_STATE["theme"]


def apply_look(force=False):
    """Maya mode: every 3D View but the Tool Box column flat Maya grey (Solid / Wireframe: the view's colour;
    Material Preview: the marketing world). Blender mode: Material Preview views back on the studio light (Blender's
    own background). Writes only what differs (each write redraws). Returns True when something changed."""
    kb = mod(".operators.key_batch3")
    maya = maya_mode_on()
    name = None
    changed = False
    for area, space in kb.view_spaces():
        sh = space.shading
        hit = False
        if sh.type == 'MATERIAL':
            if maya:
                marketing_world()
                hit = _material_maya(sh)
            else:
                name = name or studio_light()
                hit = _material_blender(sh, name)
        elif maya and sh.type in {'SOLID', 'WIREFRAME'}:
            hit = _solid_maya(sh)
        if hit or force:
            area.tag_redraw()
            changed = True
    if changed:
        redraw()
    return changed


def LOOK_KEEPER():
    if LOOK_STATE["on"]:
        try:
            apply_look()
        except (ReferenceError, AttributeError, KeyError):
            pass
    return KEEPER_INTERVAL


def maya_look():
    """The flat #5c5c5c viewport background without a theme (#41), no tooltips / in-view messages in
    the pictures. The keeper timer re-applies it to views made later; the theme is remembered so captures can check
    that nothing wrote it."""
    if LOOK_STATE["theme"] is None:
        LOOK_STATE["theme"] = theme_signature()
    LOOK_STATE["on"] = True
    apply_look(force=True)
    if not bpy.app.timers.is_registered(LOOK_KEEPER):
        bpy.app.timers.register(LOOK_KEEPER, first_interval=KEEPER_INTERVAL, persistent=True)
    bpy.context.preferences.view.show_tooltips = False
    prefs().in_view_messages = False


def viewport_rects(window=None):
    """Top-down window rects of the WINDOW regions of every 3D View that should show Maya's flat grey (Tool Box
    column excluded; quad views give four), largest first — what bg_check.py samples."""
    w = window or win()
    tb = mod(".ui.toolbox")
    out = []
    for a in w.screen.areas:
        if a.type != 'VIEW_3D' or tb.is_toolbox(a.spaces.active):
            continue
        regions = [r for r in a.regions if r.type == 'WINDOW' and r.width > 1 and r.height > 1]
        if len(regions) > 1:
            # quad view: one space, one background for its four regions; the orthographic ones may show nothing
            # but ground (DOGWALK top view), so the perspective region stands for the space
            persp = [r for r in regions if r.data is not None and r.data.view_perspective == 'PERSP']
            regions = persp[:1] or regions[-1:]
        for r in regions:
            out.append([r.x, w.height - (r.y + r.height), r.width, r.height])
    return sorted(out, key=lambda rc: -rc[2] * rc[3])


def bg_result(path, rects, window_size):
    """bg_check.py on a saved capture: (ok, per-rect results)."""
    import bg_check
    return bg_check.check_image(path, rects, window_size)


def check_capture(path, label, rects, window_size):
    """bg_check.py on a saved capture, recorded as a check (FAIL = a viewport is not Maya's flat grey), plus the
    no-theme check (FAIL = something wrote the theme since ``maya_look()``)."""
    import bg_check
    from sim import check
    ok, res = bg_result(path, rects, window_size)
    check(bg_check.summary(label, ok, res), ok)
    check(f"{label}: theme untouched (Blender's factory theme, #41)", theme_unchanged())
    return ok, res


def clear_objects():
    """Empty scene: objects, then the data they leave behind (meshes, armatures, materials, images, actions)."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for c in list(bpy.data.collections):
        if not c.get("allset_set"):
            bpy.data.collections.remove(c)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    sc = bpy.context.scene                  # the startup time range (like Maya) for every new set
    sc.frame_start, sc.frame_end = 1, 120
    sc.use_preview_range = False
    sc.frame_set(1)


def shaders_ready_step(max_ticks=120, then=2):
    """A sim step that repeats (one tick each, up to ``max_ticks``) while EEVEE still compiles shaders — Material
    Preview draws placeholder grey until it is done — then gives ``then`` more ticks for the final draw."""
    import sim
    state = {"n": 0, "after": then}

    def fn():
        redraw()
        state["n"] += 1
        busy = bpy.app.is_job_running('SHADER_COMPILATION')
        if (busy or state["n"] < 3) and state["n"] < max_ticks:
            sim._steps.insert(0, fn)
        elif state["after"] > 0:
            state["after"] -= 1
            sim._steps.insert(0, fn)
        else:
            print(f"shaders ready after {state['n']} ticks")
    return fn


def floor(on):
    """The grid floor of every 3D View (off where the set has its own ground)."""
    for a in win().screen.areas:
        if a.type == 'VIEW_3D' and not mod(".ui.toolbox").is_toolbox(a.spaces.active):
            a.spaces.active.overlay.show_floor = on
            a.spaces.active.overlay.show_axis_x = on
            a.spaces.active.overlay.show_axis_y = on
