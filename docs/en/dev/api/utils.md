---
title: liteyuki.utils
---
### *func* `is_coroutine_callable() -> bool`



**Description**: 判断是否为协程可调用对象

**Arguments**:
> - call: 可调用对象  

**Return**: bool: 是否为协程可调用对象


<details>
<summary> <b>Source code</b> </summary>

```python
def is_coroutine_callable(call: Callable[..., Any]) -> bool:
    """
    判断是否为协程可调用对象
    Args:
        call: 可调用对象
    Returns:
        bool: 是否为协程可调用对象
    """
    if inspect.isroutine(call):
        return inspect.iscoroutinefunction(call)
    if inspect.isclass(call):
        return False
    func_ = getattr(call, '__call__', None)
    return inspect.iscoroutinefunction(func_)
```
</details>

### *func* `run_coroutine()`



**Description**: 运行协程

**Arguments**:
> - coro:   


<details>
<summary> <b>Source code</b> </summary>

```python
def run_coroutine(*coro: Coroutine):
    """
    运行协程
    Args:
        coro:

    Returns:

    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            for c in coro:
                asyncio.ensure_future(c)
        else:
            for c in coro:
                loop.run_until_complete(c)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.gather(*coro))
        loop.close()
    except Exception as e:
        logger.error(f'Exception occurred: {e}')
```
</details>

### *func* `run_coroutine_in_thread()`



**Description**: 在新线程中运行协程

**Arguments**:
> - coro:   


<details>
<summary> <b>Source code</b> </summary>

```python
def run_coroutine_in_thread(*coro: Coroutine):
    """
    在新线程中运行协程
    Args:
        coro:

    Returns:

    """
    threading.Thread(target=run_coroutine, args=coro, daemon=True).start()
```
</details>

### *func* `path_to_module_name() -> str`



**Description**: 转换路径为模块名

**Arguments**:
> - path: 路径a/b/c/d -> a.b.c.d  

**Return**: str: 模块名


<details>
<summary> <b>Source code</b> </summary>

```python
def path_to_module_name(path: Path) -> str:
    """
    转换路径为模块名
    Args:
        path: 路径a/b/c/d -> a.b.c.d
    Returns:
        str: 模块名
    """
    rel_path = path.resolve().relative_to(Path.cwd().resolve())
    if rel_path.stem == '__init__':
        return '.'.join(rel_path.parts[:-1])
    else:
        return '.'.join(rel_path.parts[:-1] + (rel_path.stem,))
```
</details>

### *func* `async_wrapper() -> Callable[..., Coroutine]`



**Description**: 异步包装器

**Arguments**:
> - func: Sync Callable  

**Return**: Coroutine: Asynchronous Callable


<details>
<summary> <b>Source code</b> </summary>

```python
def async_wrapper(func: Callable[..., Any]) -> Callable[..., Coroutine]:
    """
    异步包装器
    Args:
        func: Sync Callable
    Returns:
        Coroutine: Asynchronous Callable
    """

    async def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    wrapper.__signature__ = inspect.signature(func)
    return wrapper
```
</details>

