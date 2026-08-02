# VibeFlow Sandbox

Runnable fixtures are grouped by target and scope:

- `python/minimal`: compact Python Node, base_lib, Plugin, and config fixture.
- `python/integration`: the complete Python runtime and CLI sandbox.
- `javascript/minimal`: minimal JavaScript/TypeScript AOT end-to-end build.
- `javascript/integration`: the complete TypeScript AOT, Capability, Host
  Extension, and browser sandbox.

Integration runners discover a source checkout or built distribution from
marker files. They use temporary workspaces by default and therefore do not
leave reports, build directories, dependencies, or package links in this tree.
Pass `--keep-artifacts` only when the generated files are needed for inspection.
