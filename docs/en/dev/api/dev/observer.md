---
title: liteyuki.dev.observer
---
### *func* `debounce()`



**Description**: 防抖函数


<details>
<summary> <b>Source code</b> </summary>

```python
def debounce(wait):
    """
    防抖函数
    """

    def decorator(func):

        def wrapper(*args, **kwargs):
            nonlocal last_call_time
            current_time = time.time()
            if current_time - last_call_time > wait:
                last_call_time = current_time
                return func(*args, **kwargs)
        last_call_time = None
        return wrapper
    return decorator
```
</details>

### *func* `on_file_system_event(directories: tuple[str] = True, recursive: bool = None) -> Callable[[CALLBACK_FUNC], CALLBACK_FUNC]`



**Description**: 注册文件系统变化监听器

**Arguments**:
> - directories: 监听目录们  
> - recursive: 是否递归监听子目录  
> - event_filter: 事件过滤器, 返回True则执行回调函数  

**Return**: 装饰器，装饰一个函数在接收到数据后执行


<details>
<summary> <b>Source code</b> </summary>

```python
def on_file_system_event(directories: tuple[str], recursive: bool=True, event_filter: FILTER_FUNC=None) -> Callable[[CALLBACK_FUNC], CALLBACK_FUNC]:
    """
    注册文件系统变化监听器
    Args:
        directories: 监听目录们
        recursive: 是否递归监听子目录
        event_filter: 事件过滤器, 返回True则执行回调函数
    Returns:
        装饰器，装饰一个函数在接收到数据后执行
    """

    def decorator(func: CALLBACK_FUNC) -> CALLBACK_FUNC:

        def wrapper(event: FileSystemEvent):
            if event_filter is not None and (not event_filter(event)):
                return
            func(event)
        code_modified_handler = CodeModifiedHandler()
        code_modified_handler.on_modified = wrapper
        for directory in directories:
            observer.schedule(code_modified_handler, directory, recursive=recursive)
        return func
    return decorator
```
</details>

### **class** `CodeModifiedHandler(FileSystemEventHandler)`
### `@debounce(1)`
### *method* `on_modified(self, event)`


<details>
<summary> <b>Source code</b> </summary>

```python
@debounce(1)
def on_modified(self, event):
    raise NotImplementedError('on_modified must be implemented')
```
</details>

### *method* `on_created(self, event)`


<details>
<summary> <b>Source code</b> </summary>

```python
def on_created(self, event):
    self.on_modified(event)
```
</details>

### *method* `on_deleted(self, event)`


<details>
<summary> <b>Source code</b> </summary>

```python
def on_deleted(self, event):
    self.on_modified(event)
```
</details>

### *method* `on_moved(self, event)`


<details>
<summary> <b>Source code</b> </summary>

```python
def on_moved(self, event):
    self.on_modified(event)
```
</details>

### *method* `on_any_event(self, event)`


<details>
<summary> <b>Source code</b> </summary>

```python
def on_any_event(self, event):
    self.on_modified(event)
```
</details>

### ***var*** `CALLBACK_FUNC = Callable[[FileSystemEvent], None]`

- **Type**: `TypeAlias`

- **Description**: 位置1为FileSystemEvent

### ***var*** `FILTER_FUNC = Callable[[FileSystemEvent], bool]`

- **Type**: `TypeAlias`

- **Description**: 位置1为FileSystemEvent

