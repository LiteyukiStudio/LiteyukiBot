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

### ***def*** `run_coroutine() -> None`

运行协程

Args:

    coro:



Returns:

### ***def*** `path_to_module_name(path: Path) -> str`

转换路径为模块名

Args:

    path: 路径a/b/c/d -> a.b.c.d

Returns:

    str: 模块名

### ***def*** `async_wrapper(func: Callable[..., Any]) -> Callable[..., Coroutine]`

异步包装器

Args:

    func: Sync Callable

Returns:

    Coroutine: Asynchronous Callable

### ***async def*** `wrapper() -> None`



### ***var*** `IS_MAIN_PROCESS = multiprocessing.current_process().name == 'MainProcess'`



### ***var*** `func_ = getattr(call, '__call__', None)`



### ***var*** `rel_path = path.resolve().relative_to(Path.cwd().resolve())`



### ***var*** `loop = asyncio.get_event_loop()`



### ***var*** `loop = asyncio.new_event_loop()`



