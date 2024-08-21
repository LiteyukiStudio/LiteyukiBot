---
title: liteyuki.bot.lifespan
order: 1
icon: laptop-code
category: API
---

### ***def*** `run_funcs(funcs: list[LIFESPAN_FUNC | PROCESS_LIFESPAN_FUNC]) -> None`

运行函数

Args:

    funcs:

Returns:

<details>
<summary>源代码</summary>

```python
@staticmethod
def run_funcs(funcs: list[LIFESPAN_FUNC | PROCESS_LIFESPAN_FUNC], *args, **kwargs) -> None:
    """
        运行函数
        Args:
            funcs:
        Returns:
        """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    tasks = []
    for func in funcs:
        if is_coroutine_callable(func):
            tasks.append(func(*args, **kwargs))
        else:
            tasks.append(async_wrapper(func)(*args, **kwargs))
    loop.run_until_complete(asyncio.gather(*tasks))
```
</details>

### ***class*** `Lifespan`



### &emsp; ***def*** `__init__(self) -> None`

&emsp;轻雪生命周期管理，启动、停止、重启

<details>
<summary>源代码</summary>

```python
def __init__(self) -> None:
    """
        轻雪生命周期管理，启动、停止、重启
        """
    self.life_flag: int = 0
    self._before_start_funcs: list[LIFESPAN_FUNC] = []
    self._after_start_funcs: list[LIFESPAN_FUNC] = []
    self._before_process_shutdown_funcs: list[LIFESPAN_FUNC] = []
    self._after_shutdown_funcs: list[LIFESPAN_FUNC] = []
    self._before_process_restart_funcs: list[LIFESPAN_FUNC] = []
    self._after_restart_funcs: list[LIFESPAN_FUNC] = []
    self._after_nonebot_init_funcs: list[LIFESPAN_FUNC] = []
```
</details>

### &emsp; ***@staticmethod***
### &emsp; ***def*** `run_funcs(funcs: list[LIFESPAN_FUNC | PROCESS_LIFESPAN_FUNC]) -> None`

&emsp;运行函数

Args:

    funcs:

Returns:

<details>
<summary>源代码</summary>

```python
@staticmethod
def run_funcs(funcs: list[LIFESPAN_FUNC | PROCESS_LIFESPAN_FUNC], *args, **kwargs) -> None:
    """
        运行函数
        Args:
            funcs:
        Returns:
        """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    tasks = []
    for func in funcs:
        if is_coroutine_callable(func):
            tasks.append(func(*args, **kwargs))
        else:
            tasks.append(async_wrapper(func)(*args, **kwargs))
    loop.run_until_complete(asyncio.gather(*tasks))
```
</details>

### &emsp; ***def*** `on_before_start(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册启动时的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

<details>
<summary>源代码</summary>

```python
def on_before_start(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
    """
        注册启动时的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
    self._before_start_funcs.append(func)
    return func
```
</details>

### &emsp; ***def*** `on_after_start(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册启动时的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

<details>
<summary>源代码</summary>

```python
def on_after_start(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
    """
        注册启动时的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
    self._after_start_funcs.append(func)
    return func
```
</details>

### &emsp; ***def*** `on_before_process_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册停止前的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

<details>
<summary>源代码</summary>

```python
def on_before_process_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
    """
        注册停止前的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
    self._before_process_shutdown_funcs.append(func)
    return func
```
</details>

### &emsp; ***def*** `on_after_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册停止后的函数

Args:

    func:



Returns:

    LIFESPAN_FUNC:

<details>
<summary>源代码</summary>

```python
def on_after_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
    """
        注册停止后的函数
        Args:
            func:

        Returns:
            LIFESPAN_FUNC:

        """
    self._after_shutdown_funcs.append(func)
    return func
```
</details>

### &emsp; ***def*** `on_before_process_restart(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册重启时的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

<details>
<summary>源代码</summary>

```python
def on_before_process_restart(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
    """
        注册重启时的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
    self._before_process_restart_funcs.append(func)
    return func
```
</details>

### &emsp; ***def*** `on_after_restart(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册重启后的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

<details>
<summary>源代码</summary>

```python
def on_after_restart(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
    """
        注册重启后的函数
        Args:
            func:
        Returns:
            LIFESPAN_FUNC:
        """
    self._after_restart_funcs.append(func)
    return func
```
</details>

### &emsp; ***def*** `on_after_nonebot_init(self, func: Any) -> None`

&emsp;注册 NoneBot 初始化后的函数

Args:

    func:



Returns:

<details>
<summary>源代码</summary>

```python
def on_after_nonebot_init(self, func):
    """
        注册 NoneBot 初始化后的函数
        Args:
            func:

        Returns:

        """
    self._after_nonebot_init_funcs.append(func)
    return func
```
</details>

### &emsp; ***def*** `before_start(self) -> None`

&emsp;启动前

Returns:

<details>
<summary>源代码</summary>

```python
def before_start(self) -> None:
    """
        启动前
        Returns:
        """
    logger.debug('Running before_start functions')
    self.run_funcs(self._before_start_funcs)
```
</details>

### &emsp; ***def*** `after_start(self) -> None`

&emsp;启动后

Returns:

<details>
<summary>源代码</summary>

```python
def after_start(self) -> None:
    """
        启动后
        Returns:
        """
    logger.debug('Running after_start functions')
    self.run_funcs(self._after_start_funcs)
```
</details>

### &emsp; ***def*** `before_process_shutdown(self) -> None`

&emsp;停止前

Returns:

<details>
<summary>源代码</summary>

```python
def before_process_shutdown(self) -> None:
    """
        停止前
        Returns:
        """
    logger.debug('Running before_shutdown functions')
    self.run_funcs(self._before_process_shutdown_funcs)
```
</details>

### &emsp; ***def*** `after_shutdown(self) -> None`

&emsp;停止后

Returns:

<details>
<summary>源代码</summary>

```python
def after_shutdown(self) -> None:
    """
        停止后
        Returns:
        """
    logger.debug('Running after_shutdown functions')
    self.run_funcs(self._after_shutdown_funcs)
```
</details>

### &emsp; ***def*** `before_process_restart(self) -> None`

&emsp;重启前

Returns:

<details>
<summary>源代码</summary>

```python
def before_process_restart(self) -> None:
    """
        重启前
        Returns:
        """
    logger.debug('Running before_restart functions')
    self.run_funcs(self._before_process_restart_funcs)
```
</details>

### &emsp; ***def*** `after_restart(self) -> None`

&emsp;重启后

Returns:

<details>
<summary>源代码</summary>

```python
def after_restart(self) -> None:
    """
        重启后
        Returns:

        """
    logger.debug('Running after_restart functions')
    self.run_funcs(self._after_restart_funcs)
```
</details>

### ***var*** `tasks = []`



### ***var*** `loop = asyncio.get_event_loop()`



### ***var*** `loop = asyncio.new_event_loop()`



