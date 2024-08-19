---
title: liteyuki.bot
index: true
icon: laptop-code
category: API
---

### ***def*** `get_bot() -> LiteyukiBot`

获取轻雪实例



Returns:

    LiteyukiBot: 当前的轻雪实例

### ***def*** `get_config(key: str, default: Any) -> Any`

获取配置

Args:

    key: 配置键

    default: 默认值



Returns:

    Any: 配置值

### ***def*** `get_config_with_compat(key: str, compat_keys: tuple[str], default: Any) -> Any`

获取配置，兼容旧版本

Args:

    key: 配置键

    compat_keys: 兼容键

    default: 默认值



Returns:

    Any: 配置值

### ***def*** `print_logo() -> None`



### ***class*** `LiteyukiBot`



### &emsp; ***def*** `run(self: Any) -> None`

&emsp;启动逻辑

### &emsp; ***def*** `keep_alive(self: Any) -> None`

&emsp;保持轻雪运行

Returns:

### &emsp; ***def*** `restart(self: Any, delay: int) -> None`

&emsp;重启轻雪本体

Returns:

### &emsp; ***def*** `restart_process(self: Any, name: Optional[str]) -> None`

&emsp;停止轻雪

Args:

    name: 进程名称, 默认为None, 所有进程

Returns:

### &emsp; ***def*** `init(self: Any) -> None`

&emsp;初始化轻雪, 自动调用

Returns:

### &emsp; ***def*** `init_logger(self: Any) -> None`

&emsp;

### &emsp; ***def*** `stop(self: Any) -> None`

&emsp;停止轻雪

Returns:

### &emsp; ***def*** `on_before_start(self: Any, func: LIFESPAN_FUNC) -> None`

&emsp;注册启动前的函数

Args:

    func:



Returns:

### &emsp; ***def*** `on_after_start(self: Any, func: LIFESPAN_FUNC) -> None`

&emsp;注册启动后的函数

Args:

    func:



Returns:

### &emsp; ***def*** `on_after_shutdown(self: Any, func: LIFESPAN_FUNC) -> None`

&emsp;注册停止后的函数：未实现

Args:

    func:



Returns:

### &emsp; ***def*** `on_before_process_shutdown(self: Any, func: LIFESPAN_FUNC) -> None`

&emsp;注册进程停止前的函数，为子进程停止时调用

Args:

    func:



Returns:

### &emsp; ***def*** `on_before_process_restart(self: Any, func: LIFESPAN_FUNC) -> None`

&emsp;注册进程重启前的函数，为子进程重启时调用

Args:

    func:



Returns:

### &emsp; ***def*** `on_after_restart(self: Any, func: LIFESPAN_FUNC) -> None`

&emsp;注册重启后的函数：未实现

Args:

    func:



Returns:

### &emsp; ***def*** `on_after_nonebot_init(self: Any, func: LIFESPAN_FUNC) -> None`

&emsp;注册nonebot初始化后的函数

Args:

    func:



Returns:

