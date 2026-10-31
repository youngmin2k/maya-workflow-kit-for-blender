# Component scale: Prevent Negative Scale

Double-click the Scale icon to open **Tool Settings > Scale Settings**. Enable
**Prevent Negative Scale**, or toggle it in the **R + left-click** marking menu.
The active-tool settings popup exposes the same option. It is available in mesh
Edit Mode on every Scale handle (one axis, Ctrl + axis, plane and centre); Object
Mode keeps Blender's negative scaling.

The option is on by default, as in Maya. Reset Tool restores that default. It is an addon preference, saved by Blender's normal preference-saving mechanism;
the tool does not force-save or change other Blender preferences.

Select vertices, edges/loops or faces and drag an X/Y/Z scale handle inward.
The scale factor stops at **exactly zero**, flattening fully selected points onto
the plane through the active pivot, perpendicular to that orientation axis.
A plane handle stops at zero on its two axes (the points line up on one line through
the pivot) and the centre handle on all three (the points meet at the pivot, ready
for Merge). On these handles the factor follows the mouse from the press point, so
coming back from past zero starts growing again where the drag crossed zero.
World, Object, Normal and custom orientations use their corresponding frames.
Individual Origins retains Blender's per-component centers, rather than promising
one shared plane. No vertices are welded and no edges/faces are deleted.

- Drag farther inward: the factor remains zero, without flipping the selection.
- Reverse direction: it expands from zero immediately; excess inward mouse motion
  does not have to be retraced. Every preview uses the original unflattened data.
- Type `0` to flatten exactly. Negative numbers in this guarded gesture clamp to
  zero. Disable the option for intentional negative scaling.
- Hold **J** for relative increments of **0.1**, including when pressed/released
  during a drag. Hold **Shift** for finer mouse adjustment. **Ctrl** temporarily
  inverts the persistent increment setting; J still requests snapping.
- **MMB** repeats the active axis; **Shift+MMB** chooses an axis from the drag
  direction. These routes use the same zero limit.
- Mouse release / Enter confirms; **Esc/right-click** restores the pre-drag
  coordinates and UVs. One Undo reverses the entire gesture, and Redo restores it.

The guard affects the Maya Scale tool's mesh gestures. It does not
intercept arbitrary `transform.resize` scripts, UV scaling, Smart Extrude's own
handles, or scaling in Blender mode. The guarded gesture supports increment
snapping; X/C/V geometry snapping is not evaluated by this path. Disable the option
to use Blender's native geometry-snap scaling.

Blender's transform engine still applies proportional editing, mesh symmetry,
shape-key transforms and Preserve UVs. Preview snapshots include affected points,
shape layers and (when UV correction is enabled) UV coordinates. Soft-selection
neighbors retain their native weights; they are not all forced onto the plane.
Object transformation matrices and the current pivot frame are not edited.

## References and implementation choices

[Maya 2026 Scale Tool](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Basics/files/GUID-487B6A23-E135-45E2-94F1-B0D59D6B6F33.htm)
describes non-negative component scaling and explicitly excludes objects.
[Scale marking menus](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Animation/files/GUID-8BA1A3AA-4C44-4779-8B22-0AAE3627E8EB.htm)
specifies single-axis component scaling stopping at zero.
[Scale objects and components](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Basics/files/GUID-09D0E733-74DF-44E2-937A-C857001E45B2.htm)
describes handles, pivots and MMB routes.

The docs do not fully specify negative numeric input or recovery after overshooting
zero. Numeric clamping and immediate recovery on the single-axis route are explicit
addon choices.
