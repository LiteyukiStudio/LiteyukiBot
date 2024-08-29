---
title: liteyuki.plugin.model
---
### **class** `PluginType(Enum)`
### **class** `PluginMetadata(BaseModel)`
### **class** `Plugin(BaseModel)`
### *method* `__hash__(self)`


<details>
<summary> <b>源代码</b> </summary>

```python
def __hash__(self):
    return hash(self.module_name)
```
</details>

