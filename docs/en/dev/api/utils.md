---
title: liteyuki.utils
order: 1
icon: laptop-code
category: API
---

### ***def*** `is_coroutine_callable(call: Callable[..., Any]) -> bool`

判断是否为协程可调用对象

Args:

    call: 可调用对象

Returns:

    bool: 是否为协程可调用对象

<details>
<summary>源代码</summary>

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

### ***def*** `run_coroutine() -> None`

运行协程

Args:

    coro:



Returns:

<details>
<summary>源代码</summary>

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

### ***def*** `path_to_module_name(path: Path) -> str`

转换路径为模块名

Args:

    path: 路径a/b/c/d -> a.b.c.d

Returns:

    str: 模块名

<details>
<summary>源代码</summary>

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

### ***def*** `async_wrapper(func: Callable[..., Any]) -> Callable[..., Coroutine]`

异步包装器

Args:

    func: Sync Callable

Returns:

    Coroutine: Asynchronous Callable

<details>
<summary>源代码</summary>

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

### ***async def*** `wrapper() -> None`



<details>
<summary>源代码</summary>

```python
async def wrapper(*args, **kwargs):
    return func(*args, **kwargs)
```
</details>

### ***var*** `IS_MAIN_PROCESS = multiprocessing.current_process().name == 'MainProcess'`



### ***var*** `func_ = getattr(call, '__call__', None)`



### ***var*** `rel_path = path.resolve().relative_to(Path.cwd().resolve())`



### ***var*** `loop = asyncio.get_event_loop()`



### ***var*** `loop = asyncio.new_event_loop()`



