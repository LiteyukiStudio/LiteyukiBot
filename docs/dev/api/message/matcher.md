---
title: liteyuki.message.matcher
order: 1
icon: laptop-code
category: API
---

### ***class*** `Matcher`



### &emsp; ***def*** `__init__(self, rule: Rule, priority: int, block: bool) -> None`

&emsp;匹配器

Args:

    rule: 规则

    priority: 优先级 >= 0

    block: 是否阻断后续优先级更低的匹配器

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `handle(self, handler: EventHandler) -> EventHandler`

&emsp;添加处理函数，装饰器

Args:

    handler:

Returns:

    EventHandler

<details>
<summary>源代码</summary>

```python
def handle(self, handler: EventHandler) -> EventHandler:
    """
        添加处理函数，装饰器
        Args:
            handler:
        Returns:
            EventHandler
        """
    self.handlers.append(handler)
    return handler
```
</details>

