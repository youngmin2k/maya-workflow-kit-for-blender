"""#283: on a Maya keyboard the numpad digits act like the top row — numpad 1 / 2 / 3 smooth preview, 4-7 display
modes, 0 rough display, and every other plain digit key the kit binds."""

from importlib import import_module

import kit

patches = import_module(kit.MODULE + ".keymap.maya_patches")


def _items(km, type):
    km = kit.maya_kc().keymaps[km]
    return [k for k in km.keymap_items if k.active and k.type == type and k.value == 'PRESS'
            and not (k.shift or k.ctrl or k.alt or k.oskey)]


def _props(k):
    return {p: getattr(k.properties, p) for p in k.properties.bl_rna.properties.keys() if p != "rna_type"}


def test_display_keys_on_the_numpad():
    for km in ("Object Mode", "Mesh"):
        for n, level in ((1, 1), (2, 2), (3, 3)):
            assert [(k.idname, k.properties.level) for k in _items(km, f"NUMPAD_{n}")] == \
                [("allset.smooth_preview", level)], (km, n)
    for n, mode in ((4, 'WIREFRAME'), (5, 'SHADED'), (6, 'TEXTURED'), (7, 'LIGHTS')):
        assert [(k.idname, k.properties.mode) for k in _items("3D View", f"NUMPAD_{n}")] == \
            [("allset.display_mode", mode)], n


def test_every_plain_digit_key_has_its_numpad_twin():
    twins = 0
    for km_name in {km for km, _i, e, _p, _s in patches.ADDED if e["type"] in patches.NUMPAD_DIGITS}:
        for digit, numpad in patches.NUMPAD_DIGITS.items():
            top = [(k.idname, _props(k)) for k in _items(km_name, digit) if k.idname.startswith("allset.")
                   or k.idname in {i for km, i, _e, _p, _s in patches.ADDED if km == km_name}]
            pad = [(k.idname, _props(k)) for k in _items(km_name, numpad)]
            if not top or any(not i.startswith("allset.") and i not in {a for km, a, _e, _p, _s in patches.ADDED}
                              for i, _p in pad):
                continue        # a numpad key Blender already uses there keeps its meaning
            assert pad == top, (km_name, digit, top, pad)
            twins += len(pad)
            print("  ", km_name, numpad, pad[0][0] if pad else "")
    print("numpad twins:", twins)
    assert twins >= 10
