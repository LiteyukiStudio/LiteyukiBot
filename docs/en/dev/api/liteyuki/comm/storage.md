---
title: liteyuki.comm.storage
order: 1
icon: laptop-code
category: API
---

### ***def*** `on_get(data: tuple[str, dict[str, Any]]) -> None`



### ***def*** `on_set(data: tuple[str, dict[str, Any]]) -> None`



### ***def*** `on_delete(data: tuple[str, dict[str, Any]]) -> None`



### ***def*** `on_get_all(data: tuple[str, dict[str, Any]]) -> None`



### ***class*** `KeyValueStore`



### &emsp; ***def*** `set(self: Any, key: str, value: Any) -> None`

&emsp;设置键值对

Args:

    key: 键

    value: 值

### &emsp; ***def*** `get(self: Any, key: str, default: Optional[Any]) -> Optional[Any]`

&emsp;获取键值对

Args:

    key: 键

    default: 默认值



Returns:

    Any: 值

### &emsp; ***def*** `delete(self: Any, key: str, ignore_key_error: bool) -> None`

&emsp;删除键值对

Args:

    key: 键

    ignore_key_error: 是否忽略键不存在的错误



Returns:

### &emsp; ***def*** `get_all(self: Any) -> dict[str, Any]`

&emsp;获取所有键值对

Returns:

    dict[str, Any]: 键值对

### ***class*** `GlobalKeyValueStore`



### &emsp; ***@classmethod***
### &emsp; ***def*** `get_instance(cls: Any) -> None`

&emsp;

### &emsp; ***attr*** `_instance: None`

### &emsp; ***attr*** `_lock: threading.Lock()`

