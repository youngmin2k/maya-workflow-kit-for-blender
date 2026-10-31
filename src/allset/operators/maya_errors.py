# SPDX-License-Identifier: GPL-3.0-or-later
"""Maya's ``// Error:`` messages for commands run on a selection they don't take (#152).

Maya prints these as Errors in the Command Line / Help Line (Maya 2026,
with the step-258 additions there). A kit operator reports one with ``op.report({'ERROR'}, text)``;
code that runs a Blender operator for a Maya menu item raises ``MayaError`` before it, which the menu item turns into
the same Error report (``report_nested``) instead of Blender's Python error.
"""

WRONG_SELECTION = "Current selection doesn't match required selection type."     # polyRemesh / polyReduce
NO_LIVE_SURFACE = "A live surface is required for conform."                         # Maya Mesh Tools > Conform
NO_CONFORM_SELECTION = "No components or objects selected for conform."
MUST_SELECT_JOINT = "You must select at least one joint."                           # Maya Bind Skin, no joint selected
SELECT_TO_BIND = "Select objects to bind."                     # Bind Skin, nothing selected
BINDABLE_IN_SELECTION = "Bindable objects must be part of the selection."   # Bind Skin, joints only
NO_TARGETS = "Target list was empty or contained no valid targets."                 # parent / point / orient /
#                                                    scale / aim / geometry constraint
MOVE_IK_TO_FK = "Must select an ik handle, joint or object that connected to IK/FK."   # Maya Move IK to FK
# nothing selected / a plain skeleton
REMESH_NOTHING = "This command requires at least 1 argument(s) to be specified or selected;  found 0."
REDUCE_NOTHING = "Reduce requires that at least 1 object or group of faces be selected."
NO_SHAPE = "No shape was selected."                     # KeyBlendShapeTargetsWeight on a plain skeleton / nothing


class MayaError(RuntimeError):
    """A Maya Error for the user (no traceback): ``str()`` is Blender's text for an operator's ERROR report."""

    def __init__(self, text):
        super().__init__(f"Error: {text}")
        self.text = text


# Blender can't put a hidden object into Edit / Pose / paint modes; the kit says so the Maya way (#187).
BLENDER_HIDDEN = "Cannot edit hidden object"
HIDDEN = "{} is hidden: show it (Display > Show) first"


def hidden_text(ob):
    return HIDDEN.format(ob.name if ob is not None else "The object")


def is_hidden(ob):
    return ob is not None and not ob.visible_get()


def refuse_hidden(op, ob):
    """Warn on ``op`` and return True when ``ob`` is hidden (a mode switch would fail with Blender's error)."""
    if not is_hidden(ob):
        return False
    op.report({'WARNING'}, hidden_text(ob))
    return True


def report_nested(op, ex):
    """Report a RuntimeError of a nested call on ``op``: an Error (an operator's ERROR report, a ``MayaError``) stays
    an Error with its text, anything else becomes a Warning with its last line. Blender's
    "Cannot edit hidden object" becomes the kit's warning naming the object."""
    text = str(ex).strip()
    if BLENDER_HIDDEN in text:
        import bpy
        op.report({'WARNING'}, hidden_text(bpy.context.view_layer.objects.active if bpy.context.view_layer else None))
        return
    if text.startswith("Error: ") and "Traceback" not in text:
        op.report({'ERROR'}, text[len("Error: "):].strip())
        return
    op.report({'WARNING'}, text.splitlines()[-1] if text else type(ex).__name__)


# Maya menu commands that Blender runs as a modifier on the active object (ui/menu_map._mod): which Maya check runs
# first. Remesh / Reduce: polyRemesh / polyReduce want polygon meshes; Conform wants a live
# surface (Modify > Make Live) before anything else, then a selection.
_NOTHING = {'REMESH': REMESH_NOTHING, 'DECIMATE': REDUCE_NOTHING}


def check_modifier(context, kind):
    """Raise ``MayaError`` (or a RuntimeError with a kit warning) when the Maya command behind ``object.modifier_add``
    of ``kind`` refuses this selection; return None when the modifier can be added."""
    ob = context.active_object
    nothing = context.mode == 'OBJECT' and not context.selected_objects
    if kind == 'SHRINKWRAP':
        from . import live
        if not live.objects(context.scene):
            raise MayaError(NO_LIVE_SURFACE)
        if nothing or ob is None:
            raise MayaError(NO_CONFORM_SELECTION)
        if ob.type != 'MESH':
            # Maya runs Shrinkwrap on a joint with a live surface; the message here is the kit's own
            raise RuntimeError("Conform: select a mesh to conform onto the live surface.")
        return
    if kind in _NOTHING:
        if nothing or ob is None:
            raise MayaError(_NOTHING[kind])
        if ob.type != 'MESH':
            raise MayaError(WRONG_SELECTION)
        return


def wrong_type_warning(kind):
    """Kit warning for the other Maya commands the kit runs as a modifier (Triangulate, Smooth, Soft Body ...) when
    Blender has no such modifier for the active object type: no Maya text is known for those."""
    label = {'TRIANGULATE': "Triangulate", 'SUBSURF': "Smooth", 'DATA_TRANSFER': "Transfer Attributes",
             'OCEAN': "Ocean", 'SOFT_BODY': "Soft Body"}.get(kind, str(kind).title())
    return f"{label}: select a mesh first."
