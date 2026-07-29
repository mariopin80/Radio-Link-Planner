# Third-party notice: NTIA ITM

This directory contains the NTIA ITS Irregular Terrain Model, upstream commit
`183ad95bd813a8be11009df396e1c631356864b2`.

Local integration changes made on 2026-07-28:

- converted Windows-style include separators to portable `/` separators;
- made the export macro select `__declspec(dllexport)` on Windows and
  symbol visibility attributes on Unix-like systems;
- added a local cross-platform build script outside the upstream source tree.

The upstream acknowledgment and warranty text is preserved verbatim in
`LICENSE.md`. The upstream project description is preserved in
`UPSTREAM_README.md`.

