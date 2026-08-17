# LiteyukiBot Cordis Plugin v1

Python-first in-process Cordis host for LiteyukiBot v7. Plugin authors publish
factories in the `liteyukibot.cordis_plugins` entry-point group. The root
kernel discovers one host through `liteyukibot.cordis_hosts` only when Cordis
plugins are enabled.

Cordis Plugin v1 and Native Classic Plugin v1 are independent hosts. An
extension ID is `exclusive` by default and cannot be activated in both hosts.
Both definitions must explicitly declare `infrastructure` before an ID may
coexist; this topology permission is a first-party guarantee only and remains
best-effort for third-party extensions.
