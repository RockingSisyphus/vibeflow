# Third-Party Notices

VibeFlow includes a project-local Mermaid renderer under `tools/mermaid-renderer/`.

It uses the following third-party projects to render flowcharts as SVG artifacts:

- Mermaid: https://github.com/mermaid-js/mermaid (MIT License)
- Mermaid CLI: https://github.com/mermaid-js/mermaid-cli (MIT License)
- Font Awesome Free: https://github.com/FortAwesome/Font-Awesome (Font Awesome Free License)

See the linked project repositories for their full license terms.

The offline preview includes the unmodified ELK.js 0.9.3 browser bundle
(Eclipse Public License 2.0), from the version locked by the Mermaid renderer.
Source: https://github.com/kieler/elkjs . Its license is distributed as
`tools/workflow-viewer/ELK-LICENSE.md` in source and
`vibeflow/tooling/viewer_assets/ELK-LICENSE.md` in installed packages.

The preview also includes Font Awesome Free 7.3.0 CSS and webfonts, from the same
renderer lockfile. Icons use CC BY 4.0, fonts use SIL OFL 1.1, and code uses MIT.
The upstream license accompanies these resources as `FONTAWESOME-LICENSE.txt`.
