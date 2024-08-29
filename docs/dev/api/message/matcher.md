---
title: liteyuki.message.matcher
---
### **class** `Matcher`
### *method* `__init__(self, rule: Rule, priority: int, block: bool)`



**说明**: 匹配器

**参数**:
> - rule: 规则  
> - priority: 优先级 >= 0  
> - block: 是否阻断后续优先级更低的匹配器  


<details>
<summary> <b>源代码</b> </summary>

```python
def __init__(self, rule: Rule, priority: int, block: bool):
    """
        匹配器
        Args:
            rule: 规则
            priority: 优先级 >= 0
            block: 是否阻断后续优先级更低的匹配器
        """
    self.rule = rule
    self.priority = priority
    self.block = block
    self.handlers: list[EventHandler] = []
```
</details>

### *method* `handle(self) -> Callable[[EventHandler], EventHandler]`



**说明**: 添加处理函数，装饰器

**返回**: 装饰器 handler


<details>
<summary> <b>源代码</b> </summary>

```python
def handle(self) -> Callable[[EventHandler], EventHandler]:
    """
        添加处理函数，装饰器
        Returns:
            装饰器 handler
        """

    def decorator(handler: EventHandler) -> EventHandler:
        self.handlers.append(handler)
        return handler
    return decorator
```
</details>

### *async method* `run(self, event: MessageEvent) -> None`



**说明**: 运行处理函数

**参数**:
> - event:   


<details>
<summary> <b>源代码</b> </summary>

```python
async def run(self, event: MessageEvent) -> None:
    """
        运行处理函数
        Args:
            event:
        Returns:
        """
    if not await self.rule(event):
        return
    for handler in self.handlers:
        try:
            await handler(event)
        except Exception:
            traceback.print_exc()
```
</details>

### ***var*** `EventHandler = Callable[[MessageEvent], Coroutine[None, None, Any]]`

- **类型**: `TypeAlias`

