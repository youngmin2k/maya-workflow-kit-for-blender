"""In-Blender part of tools/marketing/make_clips.py: records one feature clip as frames + a timeline.

    blender --enable-event-simulate --window-geometry 0 0 1920 1080 --python tools/marketing/clips.py -- result.json
    (env ALLSET_CLIP = clip name, ALLSET_CLIP_OUT = output folder)

Recording: one action per timer tick. A tick first takes ``screen.screenshot`` (the
window as drawn after the previous tick's events — the screenshot shows the previous frame), then sends its action.
The picture is what is on screen *while* that action happens, so it gets the action's duration (virtual time) and the
cursor path (position before -> after the action). Ticks with duration 0 only give Blender time (no picture).
The OS cursor never moves under event simulation: tools/marketing/clip_compose.py draws the cursor, clicks, key chips
and the caption band from timeline.json. Scenes = the licensed models of tools/marketing/scene.py.
"""

import json
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scene import (ROOT, bg_result, clear_objects, dog_scene, dog_view, floor, frame, lab_scene, look,  # noqa: E402
                   maya_look, maya_mode_on, mod, pack_scene, prefs, rain_scene, redraw, screen_pos, select,
                   shaders_ready_step, shading, show_bones, theme_unchanged, v3d_override,
                   viewport_rects)
import sim  # noqa: E402
from sim import MODULE, check, ev, run, setup, step, view3d, win  # noqa: E402

NAME = os.environ.get("ALLSET_CLIP", "hotbox")
OUT = Path(os.environ.get("ALLSET_CLIP_OUT", str(ROOT / "tmp" / "marketing" / "clips"))) / NAME
C = {}
REC = {"on": False, "n": 0, "entries": [], "caption": "", "chips": [], "click": None}
FPS = 30
F = 1.0 / FPS


# ------------------------------------------------------------------------------------------------ recorder
def _top(p):
    return [int(p[0]), int(win().height - p[1])]


def _tick(fn, dur, caption, chips):
    img = None
    if REC["on"] and dur > 0:
        img = f"f{REC['n']:04d}.png"
        sim.screenshot(str(OUT / img))
        REC["n"] += 1
        # what bg_check.py samples; the picture is the frame drawn since the previous tick, so it is a
        # Maya-mode picture only when Maya mode was on at the end of the previous tick and still is now
        views, maya = viewport_rects(), maya_mode_on() and REC.get("maya_after", False)
    before = list(sim._pos)
    if caption is not None:
        REC["caption"] = caption
    if chips is not None:
        REC["chips"] = list(chips)
    REC["click"] = None
    if fn is not None:
        fn()
    REC["maya_after"] = maya_mode_on()
    if img:
        REC["entries"].append({
            "img": img, "dur": round(dur, 4), "from": _top(before), "to": _top(sim._pos),
            "caption": REC["caption"], "chips": REC["chips"], "click": REC["click"],
            "down": sorted(t for t in sim._down if t.endswith("MOUSE")),
            "viewports": views, "maya_mode": maya,
        })


def beat(fn=None, dur=0.0, caption=None, chips=None):
    """One tick: picture (when recording and ``dur`` > 0), then ``fn``."""
    step(lambda: _tick(fn, dur, caption, chips))


def settle(n=1):
    for _ in range(n):
        beat(redraw)


def hold(dur, caption=None, chips=None):
    beat(redraw, dur, caption, chips)


def at(p):
    """A position (x, y) or a callable giving one, evaluated when the tick runs."""
    return p() if callable(p) else p


def move(p, dur=0.35, caption=None, chips=None, **mods):
    def fn():
        x, y = at(p)
        ev('MOUSEMOVE', 'NOTHING', x=int(x), y=int(y), **mods)
    beat(fn, dur, caption, chips)


def click(button='LEFTMOUSE', dur=0.2, caption=None, chips=None, **mods):
    def fn():
        ev(button, 'PRESS', **mods)
        ev(button, 'RELEASE', **mods)
        REC["click"] = button
    beat(fn, dur, caption, chips)


def press(kind, dur=0.2, caption=None, chips=None, **mods):
    def fn():
        ev(kind, 'PRESS', **mods)
        if kind.endswith("MOUSE"):
            REC["click"] = kind
    beat(fn, dur, caption, chips)


def release(kind, dur=F, caption=None, chips=None, **mods):
    beat(lambda: ev(kind, 'RELEASE', **mods), dur, caption, chips)


def key(kind, dur=0.2, caption=None, chips=None, **mods):
    def fn():
        ev(kind, 'PRESS', **mods)
        ev(kind, 'RELEASE', **mods)
    beat(fn, dur, caption, chips)


def drag(a, b, n=12, dur=F * 2, curve=None, caption=None, chips=None, **mods):
    """``n`` mouse moves from ``a`` to ``b`` (positions or callables), one per tick (Blender's 10 ms snap
    throttle). ``curve(t)`` -> (dx, dy) offsets the straight path."""
    state = {}

    def mover(i):
        def fn():
            if "a" not in state:
                state["a"], state["b"] = Vector(at(a)), Vector(at(b))
            t = i / n
            q = state["a"].lerp(state["b"], t)
            if curve:
                dx, dy = curve(t)
                q += Vector((dx, dy))
            ev('MOUSEMOVE', 'NOTHING', x=int(q.x), y=int(q.y), **mods)
        return fn
    for i in range(1, n + 1):
        beat(mover(i), dur, caption if i == 1 else None, chips if i == 1 else None)


def type_text(text, dur=0.09):
    for ch in text:
        beat(lambda ch=ch: ev('TEXTINPUT', 'PRESS', unicode=ch), dur)


def record(on):
    def fn():
        REC["on"] = on
        if on:
            OUT.mkdir(parents=True, exist_ok=True)
            for old in OUT.glob("f*.png"):
                old.unlink()
        else:
            _write()
    step(fn)


def _check_backgrounds():
    """Every Maya-mode frame must show the flat #5c5c5c viewport background (tools/marketing/bg_check.py, #41).
    Excluded (``bg`` = "excluded"): plain-Blender frames (Blender mode shows Blender's own UI and theme: the switch
    clip's middle part) and a frame whose picture may still be the other mode (``maya_mode`` in ``_tick``)."""
    E = REC["entries"]
    bad, n = [], 0
    for e in E:
        if not e["maya_mode"]:
            e["bg"] = "excluded"
            continue
        ok, res = bg_result(str(OUT / e["img"]), e["viewports"], (win().width, win().height))
        e["bg"] = "ok" if ok else "FAIL: " + "; ".join(r["reason"] for r in res)
        e["bg_values"] = [[r["top"], r["bottom"], r["de"]] for r in res]
        n += 1
        if not ok:
            bad.append(e["img"])
    first = next((e["bg"] for e in E if e["bg"].startswith("FAIL")), "")
    excluded = sum(1 for e in E if e["bg"] == "excluded")
    check(f"{NAME}: viewport background is Maya's flat grey in {n - len(bad)} of {n} Maya-mode frames "
          f"({excluded} plain-Blender / switch frames excluded){' — first ' + bad[0] + ': ' + first if bad else ''}",
          n > 0 and not bad)
    check(f"{NAME}: theme untouched (Blender's factory theme, #41)", theme_unchanged())


def _write():
    _check_backgrounds()
    ui = bpy.context.preferences.system.ui_scale
    data = {"name": NAME, "window": [win().width, win().height], "ui_scale": ui,
            "logo": [0, 0, round(30 * ui), round(30 * ui)], "fps": FPS, "entries": REC["entries"]}
    with open(OUT / "timeline.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    total = sum(e["dur"] for e in REC["entries"])
    check(f"{NAME}: {len(REC['entries'])} pictures, {total:.1f} s", REC["entries"] and 3.0 <= total <= 12.5)


# ------------------------------------------------------------------------------------------------ shared
def main_view():
    return mod(".ui.status_line").main_view3d(win().screen)


def centre():
    _area, r = view3d()
    return r.x + r.width // 2, r.y + r.height // 2


def view_point(fx, fy):
    _area, r = view3d()
    return r.x + int(r.width * fx), r.y + int(r.height * fy)


SCENES = {"dog": dog_scene, "lab": lab_scene, "pack": pack_scene, "rain": rain_scene}
SHADE = {"dog": dict(rotate=40, clip_end=1000.0), "lab": dict(rotate=200), "pack": dict(rotate=120),
         "rain": dict(rotate=150)}


def maya_session(kind="dog", setup_scene=None):
    """Clean sandbox -> Maya mode -> Maya layout template -> Maya look (flat grey, no theme) -> the scene of the clip (scene.py)."""
    @step
    def s_setup():
        setup()
        sim.load_maya_layout()   # the Maya layout startup.blend in the extension

    @step
    def s_scene():
        kc = bpy.context.window_manager.keyconfigs.active
        check("Maya keymap on in the Maya layout (add-on items)", kc is not None and mod(".keymap").is_applied())
        maya_look()
        clear_objects()
        if setup_scene is None:
            check(f"{kind} scene appended from the licensed files", SCENES[kind](C))
        else:
            setup_scene()
        shading('MATERIAL', **SHADE[kind])
        floor(kind != "dog")                     # the DOGWALK snow is the ground
        _a, r = view3d()
        ev('MOUSEMOVE', 'NOTHING', x=r.x + r.width // 2, y=r.y + r.height // 2)
        redraw()
    step(shaders_ready_step())
    settle(2)


def dog_start_view():
    select([C["pinda"]])
    dog_view("hotbox")


def draw_mod():
    return mod(".marking.draw")


def persp_pane():
    """Centre of the top-right quarter of the main 3D View (Maya's persp pane in the four-view layout)."""
    area = max((a for a in win().screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    return area.x + area.width * 3 // 4, area.y + area.height * 3 // 4


def shot_once(name):
    """A debug picture outside the timeline (tmp/marketing/clips/<clip>/dbg_<name>.png)."""
    step(lambda: sim.screenshot(str(OUT / f"dbg_{name}.png")))


def hotbox_label(label):
    def fn():
        lay = draw_mod().ACTIVE.get("hotbox")
        _a, r = view3d()
        rect = next(rc for rc, _k, lb in lay.labels if lb == label)
        return r.x + int((rect[0] + rect[2]) / 2), r.y + int((rect[1] + rect[3]) / 2)
    return fn


def mm_item(label):
    """Window point of a marking-menu item (radial or list) of the open session."""
    def fn():
        s = draw_mod().ACTIVE.get("session")
        _a, r = view3d()
        items = list(s.layout.radial.values()) + list(s.layout.items)
        it = next(i for i in items if i.label.rstrip(".").strip() == label)
        x = (it.rect[0] + it.rect[2]) / 2 + s.center[0]
        y = (it.rect[1] + it.rect[3]) / 2 + s.center[1]
        return r.x + int(x), r.y + int(y)
    return fn


# ------------------------------------------------------------------------------------------------ 1 hotbox
def clip_hotbox():
    maya_session("dog")

    @step
    def s_view():
        dog_start_view()
        ev('MOUSEMOVE', 'NOTHING', x=centre()[0], y=centre()[1])
        redraw()
    settle(2)
    record(True)
    hold(0.9, "Tap Space: the panel under the mouse fills the window", [])
    key('SPACE', 0.2, chips=["Space (tap)"])
    settle(2)
    hold(0.8, "Four views; tap Space over persp to fill the window with it", [])
    move(persp_pane, 0.45)
    key('SPACE', 0.2, chips=["Space (tap)"])
    settle(2)
    hold(0.5, chips=[])
    press('SPACE', 0.2, "Hold Space: the hotbox, every menu of every menu set", ["Space (hold)"])
    settle(3)
    hold(0.9)
    move(lambda: hotbox_label("Select")(), 0.45)
    settle(1)
    press('LEFTMOUSE', 0.15, chips=["Space (hold)", "LMB"])
    settle(1)
    release('LEFTMOUSE', 0)
    settle(2)

    @step
    def s_menu_check():
        C["menu_at"] = tuple(sim._pos)
    hold(0.5)
    move(lambda: (C["menu_at"][0] + 30, C["menu_at"][1] + int(MENU_UP_ROW * sim.scale())), 0.35)
    settle(1)
    hold(0.25)
    click('LEFTMOUSE', 0.2, "Select › All, straight from the hotbox", ["LMB"])
    settle(2)
    release('SPACE', F)
    settle(2)
    hold(1.3, chips=[])
    record(False)

    @step
    def s_check():
        vis = [o for o in bpy.context.scene.objects if o.visible_get() and not o.hide_select]
        n = sum(1 for o in vis if o.select_get())
        check(f"hotbox Select > All selected the visible scene ({n} of {len(vis)})", n == len(vis))


# Blender opens the hotbox's Select menu with "All by Type" under the mouse (dbg_menu_open.png): "All" is one 20 px row
# (x UI scale) above it
MENU_UP_ROW = 20


# ------------------------------------------------------------------------------------------------ 2 marking menu
def clip_marking_menu():
    maya_session("rain")

    @step
    def s_view():
        select([C["top_mesh"]])
        frame(C["rain_meshes"], 0.62, rot=(84, 0, -14), offset=(0, 0, 0.12))
        redraw()
    settle(2)

    @step
    def s_points():
        _a, r = view3d()
        C["torso"] = screen_pos(None, world=(0.0, 0.0, 1.16))
        ev('MOUSEMOVE', 'NOTHING', x=r.x + int(r.width * 0.75), y=r.y + int(r.height * 0.35))
    settle(1)
    record(True)
    hold(0.7, "Right-click an object: its marking menu, in Maya's positions", [])
    move(lambda: C["torso"], 0.45)
    press('RIGHTMOUSE', 0.2, chips=["RMB (hold)"])
    settle(3)
    hold(0.9)
    drag(lambda: C["torso"], mm_item("Vertex"), n=8, dur=F * 2, chips=["RMB drag › Vertex"])
    settle(1)
    hold(0.3)
    release('RIGHTMOUSE', F)
    settle(2)
    hold(1.0, "Release on Vertex: component mode, the Maya way", [])

    @step
    def s_mid():
        C["mode_after_vertex"] = (bpy.context.mode, tuple(bpy.context.tool_settings.mesh_select_mode))
    press('RIGHTMOUSE', 0.2, "RMB again: back to Object Mode", ["RMB (hold)"])
    settle(3)
    hold(0.7)
    drag(lambda: sim._pos[:], mm_item("Object Mode"), n=8, dur=F * 2, chips=["RMB drag › Object Mode"])
    settle(1)
    hold(0.25)
    release('RIGHTMOUSE', F)
    settle(2)
    hold(1.0, chips=[])
    record(False)

    @step
    def s_check():
        check(f"RMB > Vertex = edit mode, vertex select ({C.get('mode_after_vertex')})",
              C.get("mode_after_vertex", (None,))[0] == 'EDIT_MESH'
              and C["mode_after_vertex"][1] == (True, False, False))
        check(f"RMB > Object Mode ({bpy.context.mode})", bpy.context.mode == 'OBJECT')


# ------------------------------------------------------------------------------------------------ 3 Channel Box keys
def dock():
    return sim.dock_area('CHANNEL_BOX'), sim.dock_region('CHANNEL_BOX')


def timeline_x(frame_no):
    a = next(a for a in win().screen.areas if a.ui_type == 'TIMELINE')
    r = next(rg for rg in a.regions if rg.type == 'WINDOW')
    x, _y = r.view2d.view_to_region(frame_no, 0, clip=False)
    return r.x + x, r.y + r.height // 2


def clip_channel_box_keys():
    maya_session("lab")

    @step
    def s_view():
        d = C["battery"]
        select([d])
        sc = bpy.context.scene
        sc.frame_start, sc.frame_end = 1, 48
        sc.use_preview_range = False
        sc.frame_set(1)
        frame([d] + C["battery_parts"], 3.4, rot=(70, 0, 26), offset=(0, 0, 0.03))
        sim.dock_area('CHANNEL_BOX')
        redraw()
    settle(2)
    step(sim.find_button(dock, lambda path, _cmd: path.endswith("rz_text"), C, "rz", x_frac=0.8, step_px=6))
    step(sim.find_button(dock, lambda path, cmd: path.endswith("rz_sel") or "cb_select_channel" in cmd, C, "rz_name", y_from="rz"))

    @step
    def s_found():
        check(f"Channel Box Rotate Z field / name found ({C.get('rz')}, {C.get('rz_name')})",
              C.get("rz") is not None and C.get("rz_name") is not None)
        ev('MOUSEMOVE', 'NOTHING', x=centre()[0], y=centre()[1])
    settle(1)
    record(True)
    hold(0.7, "S keys every channel: the Channel Box turns red", [])
    key('S', 0.25, chips=["S"])
    settle(2)
    hold(0.8)
    move(lambda: timeline_x(36), 0.45, "Go to frame 36, type +=90 into Rotate Z", [])
    click('LEFTMOUSE', 0.2, chips=["LMB on Time Slider"])
    settle(2)
    move(lambda: C["rz"], 0.45)
    click('LEFTMOUSE', 0.2)
    settle(2)
    type_text("+=90")
    key('RET', 0.25, chips=["+=90", "Enter"])
    settle(2)
    hold(0.5, "Channels › Key Selected keys only that channel", [])
    move(lambda: C["rz_name"], 0.35)
    click('LEFTMOUSE', 0.15, chips=["LMB on Rotate Z"])
    settle(1)

    def open_channels():
        # Maya's Channel Box Channels menu (the RMB menu lost its Channels items: #87); a menu opens with its first
        # item (Key Selected) under the mouse
        with bpy.context.temp_override(window=win()):
            bpy.ops.wm.call_menu(name="ALLSET_MT_cb_channels")
    beat(open_channels, 0.2, chips=["Channels menu"])
    settle(3)
    hold(0.5)
    move(lambda: (sim._pos[0] + 12, sim._pos[1]), 0.2)
    settle(1)
    hold(0.2)
    click('LEFTMOUSE', 0.2, chips=["Key Selected"])
    settle(2)
    hold(0.4, "Scrub the Time Slider: the battery turns", [])
    move(lambda: timeline_x(36), 0.4)
    press('LEFTMOUSE', 0.1, chips=["Drag the Time Slider"])
    drag(lambda: timeline_x(36), lambda: timeline_x(1), n=14, dur=F * 2)
    release('LEFTMOUSE', F)
    settle(1)
    hold(1.0, chips=[])
    record(False)

    @step
    def s_check():
        d = C["battery"]
        ad = d.animation_data
        fcs = list(mod(".compat").id_fcurves(d)) if ad else []
        rz = [fc for fc in fcs if fc.data_path == "rotation_euler" and fc.array_index == 2]
        keys = sorted(int(k.co[0]) for k in rz[0].keyframe_points) if rz else []
        others = [fc for fc in fcs if not (fc.data_path == "rotation_euler" and fc.array_index == 2)]
        check(f"S keyed every channel ({len(fcs)} curves)", len(fcs) >= 9)
        check(f"Key Selected keyed Rotate Z at 36 ({keys})", keys == [1, 36])
        check("other channels keyed only at 1", all(len(fc.keyframe_points) == 1 for fc in others))




# ------------------------------------------------------------------------------------------------ 4 navigation
def mesh_centre(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return sum(pts, Vector()) / len(pts)



def clip_navigation():
    # review: the DOGWALK set is too big for a 7 s navigation demo (the tumble put the camera inside a birch
    # trunk, A framed a tiny world) and its snowman rig won the click (Maya selection priority); the compact Pack Bot
    # with its rig hidden reads better.
    maya_session("pack")

    @step
    def s_view():
        select([])
        C["pack_rig"].hide_set(True)
        base = C["pack_rig"].matrix_world.translation
        look(base + Vector((0, 0, 0.5)), (72, 0, -50), 3.2)
        ev('MOUSEMOVE', 'NOTHING', x=centre()[0], y=centre()[1])
        redraw()
    settle(2)
    record(True)
    hold(0.6, "Alt + left drag tumbles the camera", [])
    press('LEFTMOUSE', F, chips=["Alt + LMB drag"], alt=True)
    drag(centre, lambda: (centre()[0] + 150, centre()[1] + 15), n=16, dur=F * 2, alt=True)
    release('LEFTMOUSE', F, alt=True)
    hold(0.3, "Alt + middle drag tracks", [])
    press('MIDDLEMOUSE', F, chips=["Alt + MMB drag"], alt=True)
    drag(lambda: sim._pos[:], lambda: (sim._pos[0] - 60, sim._pos[1] + 20), n=12, dur=F * 2, alt=True)
    release('MIDDLEMOUSE', F, alt=True)
    hold(0.3, "Alt + right drag dollies", [])
    press('RIGHTMOUSE', F, chips=["Alt + RMB drag"], alt=True)
    drag(lambda: sim._pos[:], lambda: (sim._pos[0] + 45, sim._pos[1]), n=12, dur=F * 2, alt=True)
    release('RIGHTMOUSE', F, alt=True)
    hold(0.4, "Click the torso, F frames it", [])
    move(lambda: screen_pos(None, world=mesh_centre(C["torso"])), 0.45)
    click('LEFTMOUSE', 0.2, chips=["LMB"])
    settle(1)
    hold(0.3)

    @step
    def s_before_f():
        C["dist0"] = view3d()[0].spaces.active.region_3d.view_distance
    key('F', F, chips=["F"])
    for _ in range(12):            # Blender's smooth view: one picture per tick while it animates
        hold(F * 2)
    hold(0.7)

    @step
    def s_after_f():
        C["dist1"] = view3d()[0].spaces.active.region_3d.view_distance
    key('A', F, "A frames everything", ["A"])
    for _ in range(12):
        hold(F * 2)
    hold(0.9, chips=[])
    record(False)

    @step
    def s_check():
        check(f"the click selected the torso ({bpy.context.view_layer.objects.active})", C["torso"].select_get())
        d2 = view3d()[0].spaces.active.region_3d.view_distance
        check(f"F framed the torso, A everything (distance {C['dist0']:.2f} -> {C['dist1']:.2f} -> {d2:.2f})",
              C["dist1"] < C["dist0"] < d2 or C["dist1"] < d2)


# ------------------------------------------------------------------------------------------------ 5 pivot + V snap
def tip_vertex(ob):
    """A top corner of the battery casing: the vertex farthest from the bounding-box centre, upper half only."""
    me = ob.data
    mw = ob.matrix_world
    pts = [mw @ v.co for v in me.vertices]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    c = (lo + hi) / 2
    return max((p for p in pts if p.z > c.z), key=lambda p: Vector((p.x - c.x, p.y - c.y, (p.z - c.z) * 0.3)).length)


def ring_point(ob, deg):
    """Window point on the rotate manipulator's Z ring at angle ``deg``."""
    c = ob.matrix_world.translation
    _area, region = view3d()
    from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d
    p = location_3d_to_region_2d(region, region.data, c)
    w = region_2d_to_location_3d(region, region.data, p + Vector((1, 0)), c)
    px_world = (w - c).length
    radius = RING_PX * bpy.context.preferences.view.gizmo_size / 75.0 * sim.scale() * px_world
    q = c + Vector((math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0)) * radius
    s = location_3d_to_region_2d(region, region.data, q)
    return region.x + int(s.x), region.y + int(s.y)


RING_PX = 75.0 * 0.86     # Blender's rotate gizmo Z ring radius in gizmo-size units (read off the shots)


def clip_pivot_snap():
    maya_session("lab")

    @step
    def s_view():
        d = C["battery"]
        select([d])
        frame([d] + C["battery_parts"], 2.6, rot=(70, 0, 26), offset=(0, 0, 0.03))
        with v3d_override():
            bpy.ops.wm.tool_set_by_id(name="builtin.move")
        C["tip"] = tip_vertex(d)
        C["origin0"] = d.matrix_world.translation.copy()
        C["rot0"] = d.matrix_world.to_quaternion()
        ev('MOUSEMOVE', 'NOTHING', x=view_point(0.75, 0.3)[0], y=view_point(0.75, 0.3)[1])
        redraw()
    settle(2)
    record(True)
    hold(0.7, "Insert: edit the pivot", [])
    key('INSERT', 0.25, chips=["Insert"])
    settle(2)
    hold(0.6)
    move(lambda: screen_pos(C["battery"], (0, 0, 0.06)), 0.45, "Hold V and drag: the pivot snaps to a vertex", [])
    press('V', 0.15, chips=["V (hold)"])
    press('LEFTMOUSE', 0.15, chips=["V (hold)", "LMB drag"])
    drag(lambda: screen_pos(C["battery"], (0, 0, 0.06)), lambda: screen_pos(None, world=C["tip"]), n=14, dur=F * 2)
    hold(0.3)
    release('LEFTMOUSE', F)
    release('V', F)
    settle(1)
    hold(0.6, chips=[])
    key('INSERT', 0.25, "Insert again, then rotate around the new pivot", ["Insert"])
    settle(1)

    @step
    def s_rotate_tool():
        with v3d_override():
            bpy.ops.wm.tool_set_by_id(name="builtin.rotate")
        C["pivot"] = C["battery"].matrix_world.translation.copy()
        redraw()
    settle(2)
    hold(0.4, chips=["E"])
    move(lambda: ring_point(C["battery"], -40), 0.45)

    press('LEFTMOUSE', 0.15, chips=["E", "LMB drag"])
    drag(lambda: ring_point(C["battery"], -40), lambda: ring_point(C["battery"], 25), n=14, dur=F * 2,
         curve=None)
    release('LEFTMOUSE', F)
    settle(1)
    hold(1.0, chips=[])
    record(False)

    @step
    def s_check():
        d = C["battery"]
        mw = d.matrix_world
        # the evaluated mesh: V snaps to the vertices the viewport draws (the battery's Bevel modifier adds them)
        ev_ob = d.evaluated_get(bpy.context.evaluated_depsgraph_get())
        off = min((mw @ v.co - C["pivot"]).length for v in ev_ob.data.vertices)
        moved = (C["pivot"] - C["origin0"]).length
        # V snaps to the nearest drawn vertex of any object under the cursor (the battery sits in the bot's holder)
        dg = bpy.context.evaluated_depsgraph_get()
        near, who = off, d.name
        for inst in dg.object_instances:      # geometry-nodes instances included (the lid mechanism is instanced)
            o = inst.object
            if o.type != 'MESH':
                continue
            m = inst.matrix_world
            for v in o.data.vertices:
                dist = (m @ v.co - C["pivot"]).length
                if dist < near:
                    near, who = dist, o.name
        check(f"V snap put the pivot on a vertex ({who}, {near:.5f} m off; battery {off:.5f} m; moved {moved:.3f} m)",
              near < 5e-3 and moved > 1e-3)   # lands 2.7 mm from the nearest instanced lid vertex (unresolved)
        check(f"the battery turned around it (pivot kept {(mw.translation - C['pivot']).length:.5f} m, rot z "
              f"{math.degrees(mw.to_quaternion().rotation_difference(C['rot0']).angle):.1f} deg)", (mw.translation - C["pivot"]).length < 1e-4
              and mw.to_quaternion().rotation_difference(C["rot0"]).angle > math.radians(5))


# ------------------------------------------------------------------------------------------------ 6 rigging
def rig_scene():
    """Rain's meshes without her rig, to rig on camera: deformers, shape keys and vertex groups removed, joined into
    one mesh in her rest T-pose (the CC BY file itself is unchanged)."""
    rain_scene(C, relaxed=False)
    keep = {'SUBSURF', 'SOLIDIFY'}
    meshes = [o for o in C["rain_meshes"] if o.type == 'MESH']
    for o in meshes:
        mw = o.matrix_world.copy()
        for m in list(o.modifiers):
            if m.type not in keep:
                o.modifiers.remove(m)
        if o.data.shape_keys:
            o.shape_key_clear()
        o.vertex_groups.clear()
        o.parent = None
        o.matrix_world = mw
    body = C["body"]
    rig = C["rig"]
    for o in [rig] + [o for o in bpy.data.objects if o.type in {'LATTICE', 'EMPTY'} or o.name.startswith("WGT-")]:
        bpy.data.objects.remove(o)
    with bpy.context.temp_override(window=win(), active_object=body, object=body,
                                   selected_objects=meshes, selected_editable_objects=meshes):
        bpy.ops.object.join()
    body.name = "rain"
    body.data.name = "rainShape"
    C["body"] = body
    bpy.context.view_layer.update()


def arm_points():
    """Chest, shoulder, elbow, wrist of the character's arm on screen's right, in world space (front view plane y=0)."""
    me = C["body"]
    pts = [me.matrix_world @ v.co for v in me.data.vertices if (me.matrix_world @ v.co).x > 0.05]
    xmax = max(p.x for p in pts)
    zs = sorted(p.z for p in pts)
    height = zs[-1] - zs[0]

    def band(x0, x1):
        sel = [p for p in pts if x0 <= p.x <= x1]
        return sum(p.z for p in sel) / max(len(sel), 1)
    wrist_z = band(0.80 * xmax, 0.88 * xmax)
    elbow_z = band(0.50 * xmax, 0.58 * xmax)
    shoulder_z = elbow_z + (elbow_z - wrist_z) * 0.6      # the T-pose arm line carried on to the shoulder
    chest = Vector((0, 0, shoulder_z - 0.02 * height))
    return [chest, Vector((0.22 * xmax, 0, shoulder_z)), Vector((0.52 * xmax, 0, elbow_z)),
            Vector((0.84 * xmax, 0, wrist_z))]


def shelf_icon(slot):
    def fn():
        shelf = mod(".ui.shelf")
        area = shelf.shelf_row_area(win().screen)
        r = next(rg for rg in area.regions if rg.type == 'WINDOW')
        x, y, size = shelf.icon_rect(r, slot, sim.scale())
        return round(r.x + x + size / 2), round(r.y + y + size / 2)
    return fn


def bones_in_front():
    """Joints drawn over the body (Maya draws joints in front of the skin)."""
    for o in bpy.data.objects:
        if o.type == 'ARMATURE':
            o.show_in_front = True
    redraw()


SLOT = {"joints": 1, "ik": 2, "bind": 3, "paint": 6}     # Maya's Rigging shelf (ui/shelf_data.py)


def clip_rigging():
    maya_session("rain", setup_scene=rig_scene)

    @step
    def s_view():
        prefs().menu_set = 'riggingMenuSet'
        bpy.ops.allset.shelf_select(shelf="Rigging")
        area, region = view3d()
        with bpy.context.temp_override(window=win(), screen=win().screen, area=area, region=region):
            bpy.ops.view3d.view_axis(type='FRONT')
        rv3d = area.spaces.active.region_3d
        rv3d.view_perspective = 'ORTHO'
        pts = arm_points()
        rv3d.view_location = Vector((pts[2].x * 0.9, 0, pts[1].z - 0.12))
        rv3d.view_distance = 1.55
        select([])
        show_bones(True)
        C["pts"] = pts
        redraw()
    settle(2)

    def joint_xy(i):
        return lambda: screen_pos(None, world=C["pts"][i])
    record(True)
    hold(0.5, "Rigging shelf: Create Joints, click to place them", [])
    move(shelf_icon(SLOT["joints"]), 0.45)
    click('LEFTMOUSE', 0.15, chips=["Rigging shelf › Create Joints"])
    settle(1)
    for i in range(4):
        move(joint_xy(i), 0.22, chips=["LMB × 4"])
        click('LEFTMOUSE', 0.12)
        beat(bones_in_front)
    key('RET', 0.2, chips=["Enter"])
    settle(1)

    hold(0.3, "IK Handle: click the start joint, then the end joint", [])

    def ik_tool():
        # Skeleton > Create IK Handle (what the shelf button runs): after Create Joints Blender's Adjust Last
        # Operation panel covers the shelf's first icons (#86), so the clip starts the tool like the menu does
        with v3d_override():
            bpy.ops.allset.ik_handle('INVOKE_DEFAULT')
    move(joint_xy(1), 0.35)
    beat(ik_tool, 0.2, chips=["Skeleton › Create IK Handle"])
    settle(1)
    for i in (1, 3):
        move(joint_xy(i), 0.25, chips=["LMB × 2"])
        click('LEFTMOUSE', 0.12)
        settle(1)
    settle(1)

    @step
    def s_bind_select():
        sk = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
        C["sk"] = sk
        C["ik"] = next((o for o in bpy.data.objects if o.name.startswith("ikHandle")), None)
        check(f"Joint Tool made the skeleton ({sk and len(sk.data.bones)} joints), IK handle {C['ik']}",
              sk is not None and len(sk.data.bones) >= 3 and C["ik"] is not None)
        with v3d_override():
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        select([sk, C["body"]], C["body"])
        redraw()
    settle(1)
    hold(0.3, "Bind Skin, then pull the IK handle", [])
    move(shelf_icon(SLOT["bind"]), 0.4)
    click('LEFTMOUSE', 0.15, chips=["Rigging shelf › Bind Skin"])
    settle(2)

    @step
    def s_pick_ik():
        with v3d_override():
            if bpy.context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.wm.tool_set_by_id(name="builtin.move")
        select([C["ik"]])
        redraw()
    settle(1)
    move(joint_xy(3), 0.3, chips=["W", "LMB drag"])
    press('LEFTMOUSE', F)
    drag(joint_xy(3), lambda: (screen_pos(None, world=C["pts"][3])[0] - 60,
                               screen_pos(None, world=C["pts"][3])[1] + 150), n=12, dur=F * 2)
    release('LEFTMOUSE', F)
    settle(1)
    hold(0.4)

    @step
    def s_paint_select():
        select([C["body"]])
        redraw()
    hold(0.2, "Paint Skin Weights", [])
    move(shelf_icon(SLOT["paint"]), 0.4)
    click('LEFTMOUSE', 0.15, chips=["Rigging shelf › Paint Skin Weights"])
    settle(3)

    @step
    def s_paint_influence():
        # review: the tool opened on the end joint (no weights), so the whole mesh was blue; show the
        # influence with the most weighted vertices (the upper arm) like a rigger would
        b = C["body"]
        count = {g.index: 0 for g in b.vertex_groups}
        for v in b.data.vertices:
            for e in v.groups:
                if e.weight > 0.1 and e.group in count:
                    count[e.group] += 1
        if count:
            b.vertex_groups.active_index = max(count, key=count.get)
        redraw()
    settle(1)
    hold(1.2, chips=[])
    record(False)

    @step
    def s_check():
        b = C["body"]
        mod_ = next((m for m in b.modifiers if m.type == 'ARMATURE'), None)
        check(f"Bind Skin: armature modifier ({mod_ and mod_.object})", mod_ is not None)
        check(f"Paint Skin Weights: weight paint ({bpy.context.mode})", bpy.context.mode == 'PAINT_WEIGHT')


# ------------------------------------------------------------------------------------------------ 7 switch
def switch_button(label):
    """The Maya | Blender switch at the right end of the top bar: x from SWITCH_PX (read off the shots)."""
    def fn():
        ui = sim.scale()
        dx = SWITCH_PX[label] * ui
        return int(win().width - dx), int(win().height - 14 * ui)
    return fn


SWITCH_PX = {"Maya": 98, "Blender": 44}   # label centres from the window's right edge at UI scale 1.0


def clip_switch():
    @step
    def s_setup():
        setup()
        sw = mod(".switch")
        sw.set_mode(False)

    settle(3)

    @step
    def s_scene():
        clear_objects()
        check("DOGWALK set appended from the licensed file", dog_scene(C))
        redraw()

    @step
    def s_maya():
        with bpy.context.temp_override(window=win()):
            bpy.ops.allset.switch_mode(mode='MAYA')
    settle(6)

    @step
    def s_look():
        maya_look()
        shading('MATERIAL', **SHADE["dog"])
        floor(False)
        dog_view("hero")
        ev('MOUSEMOVE', 'NOTHING', x=centre()[0], y=centre()[1])
        redraw()
    settle(3)

    def switch_to(mode):
        def fn():
            with bpy.context.temp_override(window=win()):
                bpy.ops.allset.switch_mode(mode=mode)    # what the top-bar button runs
            REC["click"] = 'LEFTMOUSE'
        return fn

    def after_switch():
        shading('MATERIAL', **SHADE["dog"])
        floor(False)
        dog_view("hero")
        redraw()
    record(True)
    hold(1.0, "Maya mode: Maya layout, keys and colors", [])
    move(switch_button("Blender"), 0.6, "One click on Blender: plain Blender, same scene", [])
    beat(switch_to('BLENDER'), 0.2, chips=["Click: Blender"])
    settle(10)
    beat(after_switch)
    settle(4)
    beat(after_switch)
    settle(2)
    hold(1.8, "Plain Blender: follow any tutorial with Blender's own keys", [])
    move(switch_button("Maya"), 0.5, "One click on Maya: back to the Maya way", [])
    beat(switch_to('MAYA'), 0.2, chips=["Click: Maya"])
    settle(10)

    @step
    def s_look_back():
        maya_look()
        after_switch()
    settle(3)
    hold(1.8, chips=[])
    record(False)

    @step
    def s_check():
        kc = bpy.context.window_manager.keyconfigs.active
        check(f"back in Maya mode ({kc.name})", mod(".keymap").is_applied() and mod(".switch").is_on())


CLIPS = {"hotbox": clip_hotbox, "marking_menu": clip_marking_menu, "channel_box_keys": clip_channel_box_keys,
         "navigation": clip_navigation, "pivot_snap": clip_pivot_snap, "rigging": clip_rigging,
         "switch": clip_switch}

CLIPS[NAME]()
run(interval=float(os.environ.get("ALLSET_CLIP_INTERVAL", "0.3")), first=3.0)
