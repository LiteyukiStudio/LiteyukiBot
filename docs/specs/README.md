# LiteyukiBot v7 Specifications

`docs/specs/` is the normative documentation for implemented, public v7
contracts. A specification states the applicable release range, the versioned
boundary, its compatibility status, and the tests that protect it. Current
architecture pages explain how these contracts are composed; they do not
replace a specification.

Do not place proposals, release promises, or scratch designs here. Keep those
in ignored `tmp/` until implementation and focused tests exist. A public wire,
configuration, or plugin contract changes only with its owning specification
and tests in the same pull request.

- [Core Event and Action v1](core-event-action-v1.md)
- [Runtime IPC v6](runtime-ipc-v6.md)
- [Runtime IPC v5 (historical)](runtime-ipc-v5.md)
- [Runtime LYIP v1](runtime-lyip-v1.md)
- [Native Plugin and Service v1](native-plugin-service-v1.md)
- [Plugin WebUI Contribution v1](plugin-webui-contribution-v1.md)
- [Local WebUI Service v1](webui-service-v1.md)
- [Management and Command v1](management-command-v1.md)
- [Release and Maintenance v1](release-maintenance-v1.md)
- [Instance Daemon v1](instance-daemon-v1.md)
- [Configuration v5](configuration-v4.md)
- [Resources v1](resources-v1.md)
- [v6 Compatibility](v6-compatibility.md)

The old ADR tree has been removed. Use Git history for decision archaeology;
it is not a source of current contract requirements.
