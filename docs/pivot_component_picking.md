# Custom pivot editing

With a mesh selected in Object Mode or mesh Edit Mode, tap **D** or **Insert**
to enter custom pivot editing. Tap either key again to finish. Holding **D**
and using the mouse keeps the existing temporary workflow: releasing **D** exits.
A tap is an unused press shorter than 0.3 seconds.

While editing, click a visible vertex, edge or face to place and align the pivot.
Vertices use their exact position, edges their midpoint, and faces their median
centre. Vertex and edge hits take priority near their screen positions.
The manipulator handles retain priority on their own pixels.

- **Click:** position and orientation, respecting Snap Pivot Position/Orientation.
- **Shift-click:** position only.
- **Ctrl-click:** orientation only.
- **Ctrl+Shift-click:** aim the active manipulator axis at the component.

Mesh Edit Mode temporarily enables vertex, edge and face picking together and
restores the original selection mode on exit. Picking leaves the selected
components and world geometry intact. The existing cursor tool can also drag the component pivot.
The resulting custom pivot remains available for transforms.
Object Mode preserves transform channels, world geometry and child positions.

The picked orientation is shared by **Move (W)** and **Rotate (E)**. With Rotate
active in Object Mode, **D / Insert** temporarily shows the pivot move/orientation
handles so the rotation rings do not intercept component picks. Finishing pivot
editing restores the normal Rotate rings at the picked pivot, using its new axes.
In mesh Edit Mode, finishing restores the previous tool, including Rotate.

In Object Mode, the pivot orientation rings and move arrows use the same custom
frame. Dragging a ring rotates the arrows immediately, including after a component
has aligned the pivot. Repeated rotations accumulate from the displayed axes;
releasing the mouse keeps the last preview. **Esc / right-click** cancels the drag
and restores its initial frame. Object channels, mesh geometry and children stay
fixed throughout the gesture. **J** step snapping and numeric angle entry in
degrees are supported while rotating the pivot.

Hold **J** before or during a pivot handle drag to enable discrete steps; release
**J** during the drag to return to free movement. Translation steps are one scene
length unit along the pivot axes, relative to the starting pivot (or absolute
world steps when Move Absolute is selected). Rotation uses the configured angular
increment. The temporary J state preserves the previous snap preferences. Cursor
dragging in mesh component pivot editing also supports J translation steps.

The component frame uses X along an incident edge and Z along the surface normal.
At vertices or faces with several incident edges, the longest world-space edge
supplies X. This gives a stable right-handed frame under nonuniform object scale.

This follows Autodesk Maya 2026's documented D/Insert workflow and modifier clicks:

- [Activate custom pivot editing](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Basics/files/GUID-6BCE41D8-07CB-4A99-99CD-1D3986896157.htm)
- [Change the pivot point](https://help.autodesk.com/cloudhelp/2026/ENU/Maya-Basics/files/GUID-150B390E-840B-4FE3-B8E9-8DEBCE7CEC97.htm)
