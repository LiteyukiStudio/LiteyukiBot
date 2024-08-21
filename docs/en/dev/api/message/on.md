---
title: liteyuki.message.on
order: 1
icon: laptop-code
category: API
---

### ***def*** `on_message(rule: Rule, priority: int, block: bool) -> Matcher`



<details>
<summary>源代码</summary>

```python
def on_message(rule: Rule=Rule(), priority: int=0, block: bool=True) -> Matcher:
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

### ***var*** `current_priority = -1`



### ***var*** `matcher = Matcher(rule, priority, block)`



### ***var*** `current_priority = matcher.priority`



