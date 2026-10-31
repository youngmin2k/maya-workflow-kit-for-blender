"""Maya view keys 3 (Alt+A cycle display, Alt+P camera mode, Alt+arrows pixel move, ` tweak hold,
\\ 2D pan/zoom) and the mapping table's cell escaping."""

import math
import os
from importlib import import_module

import bpy

import kit

vk = import_module(kit.MODULE + ".operators.view_keys3")
patches = import_module(kit.MODULE + ".keymap.maya_patches")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_cycle_table_is_mayas():
    # switchDisplayMode: 0 -> X-ray joints (1), 1 -> everything (2), 2 -> meshes only (0)
    assert vk.cycle_next(0) == ("XRAY_JOINTS", 1)
    assert vk.cycle_next(1) == ("ALL", 2)
    assert vk.cycle_next(2) == ("MESHES", 0)


class _Space:
    show_object_viewport_armature = True
    show_object_viewport_curve = True
    show_object_viewport_mesh = True


def test_apply_display_restores_in_front():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    arm = bpy.data.objects.new("rig", bpy.data.armatures.new("rig"))
    bpy.context.scene.collection.objects.link(arm)
    arm.show_in_front = False
    sp = _Space()
    vk.apply_display(bpy.context, sp, "XRAY_JOINTS")
    assert arm.show_in_front and sp.show_object_viewport_armature
    vk.apply_display(bpy.context, sp, "ALL")
    assert not arm.show_in_front and sp.show_object_viewport_curve
    vk.apply_display(bpy.context, sp, "MESHES")
    assert not sp.show_object_viewport_armature and not sp.show_object_viewport_curve and sp.show_object_viewport_mesh


def test_ortho_scale_keeps_the_width():
    fov = math.radians(54.4)
    assert abs(vk.ortho_scale_for(10.0, fov) - 2 * 10 * math.tan(fov / 2)) < 1e-9


def test_camera_offset_follows_the_mouse():
    a = vk.camera_offset_after((0.0, 0.0), 100, 0, 1000, 500, 0.0)
    b = vk.camera_offset_after((0.0, 0.0), -100, 0, 1000, 500, 0.0)
    assert a[0] < 0 < b[0] and a[1] == 0 and abs(a[0] + b[0]) < 1e-12
    near = vk.camera_offset_after((0.0, 0.0), 100, 0, 1000, 500, 100.0)      # zoomed in: smaller step
    assert abs(near[0]) < abs(a[0])


def test_keymap_items():
    kc = kit.maya_kc()
    km = kc.keymaps["3D View"]

    def one(t, idname, **mods):
        items = [k for k in km.keymap_items if k.active and k.type == t and k.idname == idname
                 and all(getattr(k, m) == mods.get(m, False) for m in ("shift", "ctrl", "alt"))]
        assert len(items) == 1, (t, idname, mods)
        return items[0]
    one('A', "allset.cycle_display", alt=True)
    one('P', "allset.camera_mode_toggle", alt=True)
    for key, dx, dy in patches.PIXEL_MOVE_KEYS:
        k = one(key, "allset.pixel_move", alt=True)
        assert (k.properties.dx, k.properties.dy) == (dx, dy) and k.repeat
    one('ACCENT_GRAVE', "allset.tweak_hold")
    one('BACK_SLASH', "allset.pan_zoom_hold")
    assert not [k for k in kc.keymaps["Object Non-modal"].keymap_items
                if k.idname == "object.transfer_mode" and k.type == 'ACCENT_GRAVE']


def test_mapping_table_columns():
    """Every row of the generated keymap mapping table has its table's column count (a pipe in a cell is an entity)."""
    path = os.path.join(ROOT, "docs", "keymap_mapping.md")
    if not os.path.exists(path):
        raise kit.Skip("generated mapping table not in this clone")
    width, bad = None, []
    for line in open(path, encoding="utf-8"):
        if not line.startswith("|"):
            width = None
            continue
        n = line.count("|") - 1
        if width is None:
            width = n
        elif n != width:
            bad.append(line.strip())
    assert not bad, bad
    assert "Shift+&#124;" in open(path, encoding="utf-8").read()
