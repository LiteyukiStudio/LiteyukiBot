# Documentation

`docs/` contains maintained v7 contracts and operational guidance. Write facts
that match the current implementation and tested release state; do not use this
tree for scratch plans or promises about unimplemented work.

- `architecture/` describes the current system boundary and lifecycle.
- `adr/` contains accepted architecture decisions; superseded decisions remain
  for historical reasoning rather than being rewritten.
- `development/` contains contributor, plugin-author, runtime-author, and
  release-maintainer guidance.
- `archive/` holds completed historical records that remain useful for design
  or release archaeology.
- top-level documents cover configuration, compatibility, performance, and the
  current Beta1 support contract.

Keep relative Markdown links valid. Contract changes need focused tests in the
same pull request and a corresponding documentation update.
