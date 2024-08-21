---
title: liteyuki.dev.observer
order: 1
icon: laptop-code
category: API
---

### ***def*** `debounce(wait: Any) -> None`

防抖函数

<details>
<summary>源代码</summary>

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

### ***def*** `on_file_system_event(directories: tuple[str], recursive: bool, event_filter: FILTER_FUNC) -> Callable[[CALLBACK_FUNC], CALLBACK_FUNC]`

注册文件系统变化监听器

Args:

    directories: 监听目录们

    recursive: 是否递归监听子目录

    event_filter: 事件过滤器, 返回True则执行回调函数

Returns:

    装饰器，装饰一个函数在接收到数据后执行

<details>
<summary>源代码</summary>

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

### ***def*** `decorator(func: Any) -> None`



<details>
<summary>源代码</summary>

```python
def decorator(func):

    def wrapper(*args, **kwargs):
        nonlocal last_call_time
        current_time = time.time()
        if current_time - last_call_time > wait:
            last_call_time = current_time
            return func(*args, **kwargs)
    last_call_time = None
    return wrapper
```
</details>

### ***def*** `decorator(func: CALLBACK_FUNC) -> CALLBACK_FUNC`



<details>
<summary>源代码</summary>

```python
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
```
</details>

### ***def*** `wrapper() -> None`



<details>
<summary>源代码</summary>

```python
def wrapper(*args, **kwargs):
    nonlocal last_call_time
    current_time = time.time()
    if current_time - last_call_time > wait:
        last_call_time = current_time
        return func(*args, **kwargs)
```
</details>

### ***def*** `wrapper(event: FileSystemEvent) -> None`



<details>
<summary>源代码</summary>

```python
def wrapper(event: FileSystemEvent):
    if event_filter is not None and (not event_filter(event)):
        return
    func(event)
```
</details>

### ***class*** `CodeModifiedHandler(FileSystemEventHandler)`

Handler for code file changes

### &emsp; ***def*** `on_modified(self, event: Any) -> None`

&emsp;

<details>
<summary>源代码</summary>

```python
@debounce(1)
def on_modified(self, event):
    raise NotImplementedError('on_modified must be implemented')
```
</details>

### &emsp; ***def*** `on_created(self, event: Any) -> None`

&emsp;

<details>
<summary>源代码</summary>

```python
def on_created(self, event):
    self.on_modified(event)
```
</details>

### &emsp; ***def*** `on_deleted(self, event: Any) -> None`

&emsp;

<details>
<summary>源代码</summary>

```python
def on_deleted(self, event):
    self.on_modified(event)
```
</details>

### &emsp; ***def*** `on_moved(self, event: Any) -> None`

&emsp;

<details>
<summary>源代码</summary>

```python
def on_moved(self, event):
    self.on_modified(event)
```
</details>

### &emsp; ***def*** `on_any_event(self, event: Any) -> None`

&emsp;

<details>
<summary>源代码</summary>

```python
def on_any_event(self, event):
    self.on_modified(event)
```
</details>

### ***var*** `liteyuki_bot = get_bot()`



### ***var*** `observer = Observer()`



### ***var*** `last_call_time = None`



### ***var*** `code_modified_handler = CodeModifiedHandler()`



### ***var*** `current_time = time.time()`



### ***var*** `last_call_time = current_time`



