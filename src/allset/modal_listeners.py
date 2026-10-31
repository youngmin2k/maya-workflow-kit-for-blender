# SPDX-License-Identifier: GPL-3.0-or-later
"""Kit modal operators that only listen for clicks or wheel events and stay up for the whole session.

In the Maya layout these run all the time (joint / pose clicks, Channel Box wheel and channel drag). Timers that
wait until no tool is running (autosave, the tangent watches) must not count them, or they never run.
"""

import bpy

NAMES = frozenset({
    "ALLSET_OT_pose_empty_click",
    "ALLSET_OT_joint_outliner_select",
    "ALLSET_OT_cb_channel_drag",
    "ALLSET_OT_cb_wheel",
})


def tool_running(window_manager=None):
    """True while a modal operator other than the kit's listeners runs in some window."""
    wm = window_manager or bpy.context.window_manager
    for window in getattr(wm, "windows", ()):
        try:
            if any(op.bl_idname not in NAMES for op in window.modal_operators):
                return True
        except (AttributeError, ReferenceError):
            pass
    return False
