# LiteyukiBot DevCLI

`liteyuki-dev` verifies signed Alpha8 bundles, stages their complete
dependency closure into an offline profile, and exposes read-only LYF
diagnostics. Update and rollback operations are delegated to the owning
instance daemon so unmanaged processes cannot be changed accidentally.
