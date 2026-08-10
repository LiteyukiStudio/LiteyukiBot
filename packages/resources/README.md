# LiteyukiBot v7 Resources

`liteyukibot-v7-resources` provides the optional
`liteyukibot.resources@1` service for declarative, protocol-neutral resource
management in native plugins.

The service owns resource registration, field validation, principal targeting,
and capability checks. Resource providers own their data and persistence. The
first-party profile plugin uses this contract without requiring resources to
own a database or a kernel storage service.
