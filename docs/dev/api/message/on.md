---
title: liteyuki.message.on
---
### *func* `on_message(rule: Rule = empty_rule, priority: int = 0, block: bool = False) -> Matcher`


<details>
<summary> <b>源代码</b> </summary>

```python
def on_message(rule: Rule=empty_rule, priority: int=0, block: bool=False) -> Matcher:
    matcher = Matcher(rule, priority, block)
    for i, m in enumerate(_matcher_list):
        if m.priority < matcher.priority:
            _matcher_list.insert(i, matcher)
            break
    else:
        _matcher_list.append(matcher)
    return matcher
```
</details>

### *func* `on_keywords(keywords: list[str] = empty_rule, rule = 0, priority: int = False) -> Matcher`


<details>
<summary> <b>源代码</b> </summary>

```python
def on_keywords(keywords: list[str], rule=empty_rule, priority: int=0, block: bool=False) -> Matcher:

    @Rule
    async def on_keywords_rule(event: MessageEvent):
        return any((keyword in event.raw_message for keyword in keywords))
    return on_message(on_keywords_rule & rule, priority, block)
```
</details>

### ***var*** `_matcher_list = []`

- **类型**: `list[Matcher]`

### ***var*** `_queue = Queue()`

- **类型**: `Queue`

