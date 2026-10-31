# Credits — models, lighting and font in the marketing images and clips

The screenshots, key visuals and clips are taken in Blender with Maya Workflow Kit. The scenes are built from the
third-party assets below — Blender Studio / blender.org files plus one Poly Haven HDRI — downloaded by
`python tools/marketing/fetch_assets.py --active` into a local assets folder (outside the repository, not shipped
in the extension, never redistributed). URLs, sha256, the licence wording quoted from each page and the date it was
checked (2026-10-20) are in `tools/marketing/assets.json`; what is in each file is in
the local asset inventory (not in git). Public direct downloads only: no login, no subscription content, no paid
files. No Maya logo, Autodesk asset or Maya screen image is used anywhere, and no Blender logo is added.

| Asset | Author | Source | Licence | Changes we make |
|---|---|---|---|---|
| Rain v3 character rig (`rain_v3.2.blend`) | Blender Studio | https://studio.blender.org/characters/rain/v3/ | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | file unchanged; appended into our scenes, posed and keyed, skin weights painted / shown, re-lit, shown inside Blender UI screenshots and clips |
| Pack Bot character rig (Charge) | Blender Studio | https://studio.blender.org/characters/pack-bot/v1/ | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | file unchanged; appended, components selected / edited on camera, re-lit, shown in UI screenshots and clips |
| Security Bot character rig and battery prop (Charge) | Blender Studio | https://studio.blender.org/characters/security-bot/v1/ | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | file unchanged; appended, parts moved, pivots edited and snapped on camera, re-lit, shown in UI screenshots and clips |
| Blender 4.5 LTS splash scene "DOGWALK" (`blender-4.5-splash.blend`) | Blender Studio | https://www.blender.org/download/demo-files/ (file: https://download.blender.org/demo/splash/blender-4.5-splash.blend) | CC BY ([4.0](https://creativecommons.org/licenses/by/4.0/) per the Blender Studio terms; the demo page says "CC-BY") | file unchanged; opened / appended, re-framed, re-lit, shown in UI screenshots and clips |
| Cube Diorama asset bundle (optional props) | Blender Studio | https://www.blender.org/download/demo-files/ (file: https://download.blender.org/demo/bundles/bundles-3.0/asset-demo-bundle-3.0-cube-diorama.zip) | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | file unchanged; individual props placed in scenes (the "Computer" prop is not used) |
| Studio Small 09 HDRI (2K) | Sergej Majboroda / Poly Haven | https://polyhaven.com/a/studio_small_09 | [CC0 1.0](https://polyhaven.com/license) | unchanged; used as world lighting |
| Inter 4.1 (font of the captions and key visuals) | Rasmus Andersson and the Inter project authors | https://github.com/rsms/inter/releases/tag/v4.1 | SIL OFL 1.1 | unchanged (rendered into the images only) |

## Attribution lines (CC BY assets)

CC BY 4.0 needs the credit, a link to the licence and a note that the work was modified. Every image or clip that
shows one of these assets carries its line in the caption, the description next to it, or the end card (the trailer
end card lists all four). The wording follows the credit each Blender Studio page asks for:

- `Rain Rig (CC) Blender Foundation | studio.blender.org — CC BY 4.0, modified`
- `Pack Bot Rig (CC-BY) Blender Foundation | studio.blender.org — CC BY 4.0, modified`
- `Security Bot Rig (CC-BY) Blender Foundation | studio.blender.org — CC BY 4.0, modified`
- `DOGWALK (Blender 4.5 splash) (CC-BY) Blender Foundation | studio.blender.org — CC BY 4.0, modified`

One line for the trailer end card / listing description:
`3D assets: Rain, Pack Bot and Security Bot rigs and DOGWALK scene (CC BY 4.0) Blender Foundation | studio.blender.org, modified; Cube Diorama (CC0) Blender Studio; Studio Small 09 HDRI (CC0) Poly Haven.`
Licence link to show with it (or in the description): https://creativecommons.org/licenses/by/4.0/

The credit says nothing that suggests the Blender Foundation or Blender Studio endorses Maya Workflow Kit (CC BY 4.0
section 2(a)(6) / 3(a)(1)(A)(i)). CC0 assets need no credit; they are listed anyway.

## Not used

- Superseded earlier assets (files kept, status `superseded` in `assets.json`): Kenney Animated Characters
  Protagonists, Quaternius RobotExpressive, Poly Haven Drill 01, Desk Lamp Arm 01, Barrel 01, Cardboard Box 01,
  Wooden Table 01, Potted Plant 02, Metal Toolbox.
- Rejected (reasons in `assets.json` → `rejected`): blender.org Classroom (STAEDTLER / ZAP BOOK / rotring marks in its
  textures), Barcelona Pavillion (third-party architecture and furniture design, unsourced photos), 4.3 splash House of
  Chores (2D Grease Pencil, camera-projected), all CC BY-SA demo files (a promo image showing them is likely an
  adaptation that would itself have to be BY-SA), demo files without a stated licence, Blender Cloud gallery-only
  splashes, Blender Studio characters not labelled Free (subscription), Blend Swap (ad-gated downloads, provenance not
  verifiable per file), Blender Artists uploads (account needed, free-text licences), and, from earlier rounds, Poly
  Haven Camera 01 / Television 01 / boombox, Kenney Blaster Kit / Blocky / Mini / Toon, Quaternius packs, Sketchfab /
  Mixamo / 3D Warehouse.
