# Maya FX and Rendering in Blender

Maya Workflow Kit develops modeling, animation, rigging, UV and texturing work the Maya way. For FX and rendering it
keeps Maya's menus but runs **Blender's own features** from them: the FX, Rendering and lighting items call a Blender
operator or open the Blender editor that does the job. The kit does not rebuild nucleus, nCloth, Bifrost, Arnold or
Maya's render queue.

Every menu item's tooltip names the Blender feature it uses ("Maya: <item> → Blender: …"). Items Blender has nothing
for are greyed, and their tooltip (and the Help Line while it shows) says what to use instead.

## FX works in metre scenes

Blender simulates one unit as one metre. The kit does **not** rescale gravity, cloth stiffness, collision distances,
particle sizes or field strengths, so a simulation behaves exactly as it does in plain Blender:

- In a scene with metre units (Blender's own startup scene, or the **Maya Units** preference off), simulations run at
  real size.
- In the Maya Workflow Kit layout (centimetres, 100 units = 1 m), a 100-unit cube is a 1 m cube to the simulation;
  smaller objects fall and fold like small real objects. For FX work, model at metre scale or simulate in a metre
  scene.

Scenes saved with an earlier version that scaled FX are tidied once when they are opened: a scene gravity the kit had
scaled goes back to Blender's 9.81 m/s², and cloth stiffness / damping the kit had scaled go back to their unscaled
values.

## FX

| Maya menu item | Blender feature it runs |
|---|---|
| nParticles > Emit from Object | Particle System modifier on every selected mesh |
| nParticles > Fill Object | Particle system emitting from the volume on a grid |
| nParticles > Instancer | Particle Render As Object / Collection |
| nParticles > Soft Body | Soft Body modifier |
| nParticles > Make Collide | Collision modifier on every selected mesh |
| nCloth > Create nCloth | Cloth modifier on every selected mesh |
| nCloth > Create Passive Collider | Collision modifier on every selected mesh |
| nCloth > Remove nCloth | Removes the Cloth modifier |
| nCloth > Display Input Mesh / Current Mesh | Shows the mesh without / with the Cloth modifier in the viewport |
| nCloth > Rest Shape | Cloth Shape > Rest Shape Key (the selected mesh becomes the rest shape key) |
| nCloth > Paint Vertex Properties | Weight Paint on the Cloth vertex group (Pin, Structural, Bending, Shrinking) |
| nConstraint > Transform Constraint | Hook to New Object (put the Hook before the Cloth modifier, pin the hooked vertices) |
| nCache > Create New Cache / Delete Cache | Point cache Bake / Free Bake |
| nCache > Create Particle Disk Cache | Particle point cache baked to disk |
| nCache > Edit Oversampling or Cache Settings | Physics properties |
| Fields/Solvers > Air, Drag, Newton, Radial, Turbulence, Vortex | Force Field empties (Wind, Drag, Force, Turbulence, Vortex) |
| Fields/Solvers > Gravity / Uniform | A Wind force field blowing down / along +X |
| Fields/Solvers > Volume Curve | Curve Guide force field on the selected curve |
| Fields/Solvers > Use Selected as Source | Force field on the selected object itself |
| Fields/Solvers > Create Active / Passive Rigid Body | Rigid Body (Active / Passive) |
| Fields/Solvers > Set Active Key / Set Passive Key | Rigid body Animated checkbox, keyed |
| Fields/Solvers > Create Pin / Hinge / Spring Constraint | Rigid body constraints (Point, Hinge, Generic Spring) |
| Fields/Solvers > Set Rigid Body Interpenetration | Generic rigid body constraint with Disable Collisions |
| Fields/Solvers > Break Rigid Body Connections | Removes the rigid body, keeping the simulated transform |
| Fields/Solvers > Create Rigid Body Solver / Solver Attributes | Rigid Body World (Scene properties) |
| Fields/Solvers > Interactive Playback | Play |
| Fluids > 3D Container, Add/Edit Contents > Emit from Object | Quick Smoke (Mantaflow domain + flow) |
| Fluids > Add/Edit Contents > Emitter | The selected mesh becomes a Fluid Flow |
| Fluids > Edit Fluid Resolution | The domain's resolution |
| Fluids > Make Collide, Effects > Collide with Effect | Fluid modifier of type Effector |
| Fluids > Ocean | Ocean modifier |
| Effects > Fire / Smoke | Quick Smoke (Fire / Smoke) |
| Effects > Flow > Create Curve Flow | Curve Guide force field on the selected curve |
| nHair > Create Hair, Paint Hair Follicles | Curves hair object on the selected surface, groomed in Sculpt mode |
| nHair > Modify Curves | The kit's curve tools (Smooth, Straighten, Bend, Curl, Lock Length …) |
| Windows > Bifrost Graph Editor | Geometry Nodes editor |

## Lights

| Maya menu item | Blender feature it runs |
|---|---|
| Create > Lights > Directional / Point / Spot / Area Light | Sun / Point / Spot / Area light |
| Create > Lights > Dome Light | An environment texture on the World |
| Lighting/Shading > Make / Break Light Links | Light Linking: the selected objects are included in / excluded from the active light's receivers |
| Lighting/Shading > Make / Break Shadow Links | Light Linking blockers of the active light |
| Lighting/Shading > Select Objects Illuminated / Shadowed by Light | Selects the active light's receivers / blockers |
| Lighting/Shading > Light Linking Editor, Windows > Relationship Editors > Light Linking | Object properties of the light (Light Linking panel) |
| Windows > Rendering Editors > Light Editor | An Outliner window that lists only the lights |

Light Intensity and Decay Rate rows stay in the Channel Box and Attribute Editor.

Blender lights everything a light has no Exclude link for, until the light gets its first Include link: from then on
it lights only its included objects.

## Rendering

| Maya menu item | Blender feature it runs |
|---|---|
| Render > Render Current Frame, Redo Previous Render | Render Image (the scene camera, at the Output properties size; without one: persp, placed where the view looks from) |
| Render > Render Sequence, Batch Render | Render Animation in this Blender session (Esc stops it; without a scene camera: persp, placed where the view looks from) |
| Render > Show Batch Render, Windows > Rendering Editors > Render View | The Render window |
| Render > IPR Render Current Frame | The viewport in Rendered shading |
| Render > Test Resolution | Output properties > Resolution % (10 % to 150 %) |
| Render > Render Using | Render engine (EEVEE, Cycles, Workbench) |
| Render > Render Settings, Windows > Rendering Editors > Render Settings | A window with Blender's Render properties |
| Windows > Rendering Editors > Render Setup | View Layer properties |
| Render View > Keep Image | Render Result slots |
| Hypershade > Create > Rendering > Render Layer | A new View Layer |
| Lighting/Shading > Transfer Maps | Cycles Bake, Selected to Active |
| Create > Cameras > Stereo Camera, Stereo > Create | Camera with Render > Stereoscopy |
| Toon > Assign Fill Shader | Shader to RGB + constant Color Ramp (EEVEE) |
| Toon > Assign Outline | Line Art (Grease Pencil) |
| Toon > Set Camera Background Color | World colour |

Ctrl+F12 runs Blender's Render Animation and F12 Render Image; over the 3D View and the UV Editor F12 stays Maya's
UV selection key. No extra default light is added at render time: a render is lit by the scene's lights and World.

## Hypershade and materials

| Maya | Blender |
|---|---|
| Hypershade window | Shader Editor with the kit's Browser, Create, Material Viewer and Property Editor panes |
| Shading group | Material slot (Lighting/Shading > Assign … Material) |
| lambert1 | The kit's default material on new meshes |
| Maya shader types (Lambert, Blinn, Phong, Standard Surface …) | Principled BSDF materials with Maya's Attribute Editor sections |
| Volume Shader, Volume Fog, Light Fog | Principled Volume / Volume Scatter on the material's Volume output |
| Env Fog | Principled Volume on the World's Volume output |
| Hair Physical / Hair Tube Shader | Principled Hair BSDF |
| USD Preview Surface | Principled BSDF (exported as UsdPreviewSurface) |

## What stays greyed

Blender has no counterpart for these, so they are greyed with a notice saying what to use instead:

- **FX**: Create Emitter (add a particle system to a mesh instead), Create Options, the nucleus node and Space Scale
  (scene gravity is in Scene properties, solver settings are per object), Initial State and Transfer Cache To Input
  Mesh (apply the Cloth modifier on the frame you want), Set Rigid Body Collision, Assign to Selected (use the Effector
  Collection of the simulation), Delete Selected Flow, nConstraints other than Transform Constraint, nCloth texture
  maps, merging or editing cache frames, nHair follicles and hair system display modes, 2D fluid containers, ponds,
  boats and wakes, Fireworks / Lightning / Shatter effects.
- **Lights**: Ambient Light (raise the World colour, or add a Point Light), Volume Light (add a Point Light), Select
  Lights Illuminating / Shadowing Object (Blender links from the light only).
- **Rendering**: Cancel Batch Render (Esc in the Render window stops a running render), toon line attributes painted
  as maps, PSD networks.
- **Hypershade**: Maya-only nodes (quaternion and matrix utilities, switch utilities, Maya procedural textures without
  a Blender texture).
