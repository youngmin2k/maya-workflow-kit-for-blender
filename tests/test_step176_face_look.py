"""Maya selected-face look (no Blender face tint under the kit stipple) and Maya camera labels."""

import importlib

from kit import MODULE


def _cc():
    return importlib.import_module(MODULE + ".ui.component_colors")


def test_face_overlay_switch_rules():
    act = _cc().face_overlay_action
    # kit draws the Maya look: Blender's tint goes off and the kit owns that switch
    assert act(True, True, False) == (False, True)
    # already off by the user: nothing to write, not the kit's switch
    assert act(True, False, False) == (None, False)
    # already switched by the kit: nothing to write, still ours
    assert act(True, False, True) == (None, True)
    # kit stops drawing (preference off / big mesh): only the kit's own switch is undone
    assert act(False, False, True) == (True, False)
    assert act(False, False, False) == (None, False)
    assert act(False, True, False) == (None, False)


def test_maya_camera_labels():
    vf = importlib.import_module(MODULE + ".ui.view_furniture")
    # Maya's camera names with Maya's Y-up view direction
    assert vf.label_for('ORTHO', True, (0.0, 0.0, -1.0)) == "top -Y"
    assert vf.label_for('ORTHO', True, (0.0, 1.0, 0.0)) == "front -Z"
    assert vf.label_for('ORTHO', True, (-1.0, 0.0, 0.0)) == "side -X"
    assert vf.label_for('ORTHO', True, (0.0, 0.0, 1.0)) == "bottom +Y"
    assert vf.label_for('ORTHO', True, (0.0, -1.0, 0.0)) == "back +Z"
    assert vf.label_for('ORTHO', True, (1.0, 0.0, 0.0)) == "left +X"
