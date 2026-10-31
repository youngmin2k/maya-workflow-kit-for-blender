"""Lane MEDIA (#41): the store / marketing / release media generators never apply a theme.

The kit ships no theme (#40); the promotional shots use Blender's factory theme and get a flat
#5c5c5c viewport from view / scene data (tools/marketing/scene.py ``maya_look``). This test fails when a generator
writes a theme again (static scan of the generators) and checks tools/marketing/bg_check.py, which every shot
runs: flat Maya grey passes, Blender's factory theme background and the old kit theme gradient fail.
"""

import ast
import os
import sys

import bpy
import numpy as np

AUTO_ENABLE = False
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATORS = [os.path.join("tools", "marketing", f) for f in sorted(os.listdir(os.path.join(ROOT, "tools", "marketing")))
              if f.endswith(".py")] + [os.path.join("tools", f) for f in
                                       ("release_shots.py", "release_check.py", "make_listing_media.py")] + \
    [os.path.join("tools", "site", "make_media.py")]
# Names / attributes that only appear when code applies or edits a theme.
BANNED = {"rna_xml", "_rna_xml", "make_maya", "gradients", "reset_default_theme", "interface_theme_preset_add",
          "theme_apply", "apply_theme"}


def _themeish(node):
    text = ast.unparse(node)
    return "themes" in text or "theme_area" in text


def violations(source, name="<src>"):
    """Theme writes in Python source: banned names, assignments to a theme path or to a name bound to one."""
    tree = ast.parse(source)
    out = []
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _themeish(node.value):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    aliases.add(t.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in BANNED:
            out.append(f"{name}:{node.lineno}: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in BANNED:
            out.append(f"{name}:{node.lineno}: .{node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in BANNED:
            out.append(f"{name}:{node.lineno}: '{node.value}'")
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    continue
                root = t
                while isinstance(root, (ast.Attribute, ast.Subscript)):
                    root = root.value
                if _themeish(t) or (isinstance(root, ast.Name) and root.id in aliases):
                    out.append(f"{name}:{node.lineno}: writes {ast.unparse(t)}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr" \
                and node.args and (_themeish(node.args[0]) or
                                   (isinstance(node.args[0], ast.Name) and node.args[0].id in aliases)):
            out.append(f"{name}:{node.lineno}: setattr on a theme")
    return out


def test_scanner_catches_the_step125_gradient_write():
    old = ("def apply_gradient():\n"
           "    g = bpy.context.preferences.themes[0].view_3d.space.gradients\n"
           "    g.background_type = 'LINEAR'\n"
           "    g.high_gradient = (0.5, 0.6, 0.7)\n"
           "    bpy.context.preferences.themes[0].view_3d.space.back = (0, 0, 0)\n"
           "    bpy.ops.allset.make_maya(open_layout=False)\n")
    found = violations(old)
    assert len(found) >= 4, found
    ok = ("def sig():\n    t = bpy.context.preferences.themes[0]\n    return repr(t.view_3d)\n"
          "def look(sh):\n    sh.background_type = 'VIEWPORT'\n")
    assert violations(ok) == [], violations(ok)


def test_generators_write_no_theme():
    found = []
    for rel in GENERATORS:
        path = os.path.join(ROOT, rel)
        assert os.path.isfile(path), rel
        with open(path, encoding="utf-8") as fh:
            found += violations(fh.read(), rel.replace(os.sep, "/"))
    assert not found, "generators apply / edit a theme (#41):\n" + "\n".join(found)


def _png(path, rows):
    """A 400 x 300 PNG whose rows (top-down) have the colours of ``rows(t)`` (sRGB 0..255), t = 0 top .. 1 bottom."""
    w, h = 400, 300
    px = np.zeros((h, w, 4), dtype=np.float32)
    for y in range(h):                       # Blender images are bottom-up
        px[h - 1 - y, :, :3] = np.array(rows(y / (h - 1)), dtype=np.float32) / 255.0
    px[..., 3] = 1.0
    img = bpy.data.images.new("bg142", w, h)
    img.colorspace_settings.name = 'Non-Color'          # write the numbers as they are
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)


def test_bg_check_wants_flat_maya_grey():
    sys.path.insert(0, os.path.join(ROOT, "tools", "marketing"))
    import bg_check
    out = os.path.join(ROOT, "tmp", "test_env", "bg142")
    os.makedirs(out, exist_ok=True)
    rect = [[0, 0, 400, 300]]
    cases = {
        "maya_flat": (lambda t: (92, 92, 92), True),
        "material_preview_agx": (lambda t: (90, 90, 90), True),
        "blender_factory_theme": (lambda t: (61, 61, 61), False),
        "step125_gradient": (lambda t: tuple(a + (b - a) * t for a, b in zip((0x88, 0x9d, 0xb3), (13, 13, 13))), False),
        "maya_light_grey": (lambda t: (161, 161, 161), False),
    }
    for name, (rows, want) in cases.items():
        path = os.path.join(out, name + ".png")
        _png(path, rows)
        ok, res = bg_check.check_image(path, rect)
        assert ok is want, (name, res)
    # objects in the lower part (a ground) don't fail a flat top
    path = os.path.join(out, "ground.png")
    _png(path, lambda t: (92, 92, 92) if t < 0.4 else (220, 225, 230))
    ok, res = bg_check.check_image(path, rect)
    assert ok, res
