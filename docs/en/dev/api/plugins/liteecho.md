---
title: liteyuki.plugins.liteecho
---
### `@on_startswith(['liteecho'], rule=is_su_rule).handle()`
### *async func* `liteecho()`


<details>
<summary> <b>Source code</b> </summary>

```python
@on_startswith(['liteecho'], rule=is_su_rule).handle()
async def liteecho(event: MessageEvent):
    event.reply(event.raw_message.strip()[8:].strip())
```
</details>

