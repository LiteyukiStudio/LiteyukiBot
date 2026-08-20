"""Reject the removed legacy child-runtime launch path."""

raise SystemExit(
    "migration_required: liteyukibot-v7-runtime-mofox is a broker bridge; "
    "configure it under broker.bridges and use 'liteyuki bridge run'"
)
