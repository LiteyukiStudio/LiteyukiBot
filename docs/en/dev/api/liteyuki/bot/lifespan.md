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

### ***def*** `on_before_start(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

注册启动时的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

### ***def*** `on_after_start(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

注册启动时的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

### ***def*** `on_before_process_shutdown(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

注册停止前的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

### ***def*** `on_after_shutdown(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

注册停止后的函数
Args:
    func:

Returns:
    LIFESPAN_FUNC:

### ***def*** `on_before_process_restart(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

注册重启时的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

### ***def*** `on_after_restart(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

注册重启后的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

### ***def*** `on_after_nonebot_init(self: Any, func: Any) -> None`

注册 NoneBot 初始化后的函数
Args:
    func:

Returns:

### ***def*** `before_start(self: Any) -> None`

启动前
Returns:

### ***def*** `after_start(self: Any) -> None`

启动后
Returns:

### ***def*** `before_process_shutdown(self: Any) -> None`

停止前
Returns:

### ***def*** `after_shutdown(self: Any) -> None`

停止后
Returns:

### ***def*** `before_process_restart(self: Any) -> None`

重启前
Returns:

### ***def*** `after_restart(self: Any) -> None`

重启后
Returns:

### ***class*** `Lifespan`



#### `@staticmethod`

#### &emsp; ***def*** `run_funcs(funcs: list[LIFESPAN_FUNC | PROCESS_LIFESPAN_FUNC]) -> None`

   运行函数
Args:
    funcs:
Returns:

#### &emsp; ***def*** `on_before_start(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

   注册启动时的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

#### &emsp; ***def*** `on_after_start(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

   注册启动时的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

#### &emsp; ***def*** `on_before_process_shutdown(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

   注册停止前的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

#### &emsp; ***def*** `on_after_shutdown(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

   注册停止后的函数
Args:
    func:

Returns:
    LIFESPAN_FUNC:

#### &emsp; ***def*** `on_before_process_restart(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

   注册重启时的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

#### &emsp; ***def*** `on_after_restart(self: Any, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC`

   注册重启后的函数
Args:
    func:
Returns:
    LIFESPAN_FUNC:

#### &emsp; ***def*** `on_after_nonebot_init(self: Any, func: Any) -> None`

   注册 NoneBot 初始化后的函数
Args:
    func:

Returns:

#### &emsp; ***def*** `before_start(self: Any) -> None`

   启动前
Returns:

#### &emsp; ***def*** `after_start(self: Any) -> None`

   启动后
Returns:

#### &emsp; ***def*** `before_process_shutdown(self: Any) -> None`

   停止前
Returns:

#### &emsp; ***def*** `after_shutdown(self: Any) -> None`

   停止后
Returns:

#### &emsp; ***def*** `before_process_restart(self: Any) -> None`

   重启前
Returns:

#### &emsp; ***def*** `after_restart(self: Any) -> None`

   重启后
Returns:

