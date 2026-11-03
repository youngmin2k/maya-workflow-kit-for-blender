"""Help links (main menu Help, editor Help menus, Layer Editor, Outliner) open the Blender manual / API / release
notes of the supported Blender version."""

import os
import re

import kit  # noqa: F401  (enables the kit)

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "allset")
SUPPORTED = "5.2"
LINK = re.compile(r"(?:docs\.blender\.org/(?:manual/[a-z_A-Z]+|api)|developer\.blender\.org/docs/release_notes)/"
                  r"(\d+\.\d+)/")


def test_every_versioned_blender_link_is_the_supported_version():
    found, wrong = 0, []
    for root, _dirs, files in os.walk(SRC):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    for version in LINK.findall(line):
                        found += 1
                        if version != SUPPORTED:
                            wrong.append(f"{os.path.relpath(path, SRC)}:{n} {version}")
    assert found >= 5, found
    assert not wrong, wrong
