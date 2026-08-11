# LiteyukiBot NoneBot Runtime

`liteyukibot-v7-runtime-nonebot` hosts NoneBot2 as a supervised LiteyukiBot v7
child runtime. It is discovered through the `liteyukibot.runtimes` entry-point
group, so a configuration with `kind = "nonebot"` needs no explicit command.

Install the base host and one adapter family:

```bash
uv add "liteyukibot-v7-runtime-nonebot[onebot]"
```

The runtime converts NoneBot events and actions into LiteyukiBot's frozen
Event/Action schemas. NoneBot plugins, adapters, drivers, and Bot objects stay
inside this child process.
