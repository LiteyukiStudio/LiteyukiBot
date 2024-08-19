---
title: liteyuki.dev.observer
order: 1
icon: laptop-code
category: API
---

### ***def*** `debounce(wait: Any) -> None`

防抖函数

### ***def*** `on_file_system_event(directories: tuple[str], recursive: bool, event_filter: FILTER_FUNC) -> Callable[[CALLBACK_FUNC], CALLBACK_FUNC]`

注册文件系统变化监听器
Args:
    directories: 监听目录们
    recursive: 是否递归监听子目录
    event_filter: 事件过滤器, 返回True则执行回调函数
Returns:
    装饰器，装饰一个函数在接收到数据后执行

### ***def*** `decorator(func: Any) -> None`



### ***def*** `on_modified(self: Any, event: Any) -> None`



### ***def*** `on_created(self: Any, event: Any) -> None`



### ***def*** `on_deleted(self: Any, event: Any) -> None`



### ***def*** `on_moved(self: Any, event: Any) -> None`



### ***def*** `on_any_event(self: Any, event: Any) -> None`



### ***def*** `decorator(func: CALLBACK_FUNC) -> CALLBACK_FUNC`



### ***def*** `wrapper() -> None`



### ***def*** `wrapper(event: FileSystemEvent) -> None`



### ***class*** `CodeModifiedHandler(FileSystemEventHandler)`

Handler for code file changes

#### &emsp; ***def*** `on_modified(self: Any, event: Any) -> None`

   

#### &emsp; ***def*** `on_created(self: Any, event: Any) -> None`

   

#### &emsp; ***def*** `on_deleted(self: Any, event: Any) -> None`

   

#### &emsp; ***def*** `on_moved(self: Any, event: Any) -> None`

   

#### &emsp; ***def*** `on_any_event(self: Any, event: Any) -> None`

   

