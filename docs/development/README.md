# Development Documentation

This directory contains maintained guides for plugin authors, custom-runtime
authors, and release maintainers. Keep commands executable against the current
workspace and describe only implemented contracts.

- `native-plugins.md` describes the in-process plugin boundary.
- `custom-runtimes.md` describes the implemented broker-peer foundation and
  preserves the former supervised child-runtime guidance as historical context.
- `releasing.md` records the historical B7 package procedure and the boundary
  for the planned Alpha release process. It does not authorize a release.

The forward-looking [v7 Alpha roadmap](../roadmap/v7-alpha-roadmap.md) is the
reference for sequencing Plugin API, Permission, broker, adapter, Agent, DSL,
and tooling work. Planned interfaces in that document are not current
contracts until their corresponding specification and implementation land.
