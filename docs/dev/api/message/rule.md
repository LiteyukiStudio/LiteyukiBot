---
title: liteyuki.message.rule
---
### `@Rule`
### *async func* `empty_rule() -> bool`


<details>
<summary> <b>源代码</b> </summary>

```python
@Rule
async def empty_rule(event: MessageEvent) -> bool:
    return True
```
</details>

### `@Rule`
### *async func* `is_su_rule() -> bool`


<details>
<summary> <b>源代码</b> </summary>

```python
@Rule
async def is_su_rule(event: MessageEvent) -> bool:
    return str(event.user_id) in _superusers
```
</details>

### **class** `Rule`
### *method* `__init__(self, handler: RuleHandlerFunc)`


<details>
<summary> <b>源代码</b> </summary>

```python
def __init__(self, handler: RuleHandlerFunc):
    self.handler = handler
```
</details>

### *method* `__or__(self, other: Rule) -> Rule`


<details>
<summary> <b>源代码</b> </summary>

```python
def __or__(self, other: 'Rule') -> 'Rule':

    async def combined_handler(event: MessageEvent) -> bool:
        return await self.handler(event) or await other.handler(event)
    return Rule(combined_handler)
```
</details>

### *method* `__and__(self, other: Rule) -> Rule`


<details>
<summary> <b>源代码</b> </summary>

```python
def __and__(self, other: 'Rule') -> 'Rule':

    async def combined_handler(event: MessageEvent) -> bool:
        return await self.handler(event) and await other.handler(event)
    return Rule(combined_handler)
```
</details>

### *async method* `__call__(self, event: MessageEvent) -> bool`


<details>
<summary> <b>源代码</b> </summary>

```python
async def __call__(self, event: MessageEvent) -> bool:
    if self.handler is None:
        return True
    return await self.handler(event)
```
</details>

### ***var*** `_superusers = get_config('liteyuki.superusers', [])`

- **类型**: `list[str]`

### ***var*** `RuleHandlerFunc = Callable[[MessageEvent], Coroutine[None, None, bool]]`

- **类型**: `TypeAlias`

- **说明**: 规则函数签名

