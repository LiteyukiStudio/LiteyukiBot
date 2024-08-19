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

### ***class*** `Lifespan`



### &emsp; ***def*** `__init__(self) -> None`

&emsp;轻雪生命周期管理，启动、停止、重启

### &emsp; ***@staticmethod***
### &emsp; ***def*** `run_funcs(funcs: list[LIFESPAN_FUNC | PROCESS_LIFESPAN_FUNC]) -> None`

&emsp;运行函数

Args:

    funcs:

Returns:

### &emsp; ***def*** `on_before_start(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册启动时的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

### &emsp; ***def*** `on_after_start(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册启动时的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

### &emsp; ***def*** `on_before_process_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册停止前的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

### &emsp; ***def*** `on_after_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册停止后的函数

Args:

    func:



Returns:

    LIFESPAN_FUNC:

### &emsp; ***def*** `on_before_process_restart(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册重启时的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

### &emsp; ***def*** `on_after_restart(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

&emsp;注册重启后的函数

Args:

    func:

Returns:

    LIFESPAN_FUNC:

### &emsp; ***def*** `on_after_nonebot_init(self, func: Any) -> None`

&emsp;注册 NoneBot 初始化后的函数

Args:

    func:



Returns:

### &emsp; ***def*** `before_start(self) -> None`

&emsp;启动前

Returns:

### &emsp; ***def*** `after_start(self) -> None`

&emsp;启动后

Returns:

### &emsp; ***def*** `before_process_shutdown(self) -> None`

&emsp;停止前

Returns:

### &emsp; ***def*** `after_shutdown(self) -> None`

&emsp;停止后

Returns:

### &emsp; ***def*** `before_process_restart(self) -> None`

&emsp;重启前

Returns:

### &emsp; ***def*** `after_restart(self) -> None`

&emsp;重启后

Returns:

