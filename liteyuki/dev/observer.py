"""
此模块用于注册观察者函数，使用watchdog监控文件变化并重启bot
启用该模块需要在配置文件中设置`dev_mode`为True
"""
import time
from typing import Callable, TypeAlias

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from liteyuki import get_bot, get_config_with_compat, logger

liteyuki_bot = get_bot()

CALLBACK_FUNC: TypeAlias = Callable[[FileSystemEvent], None]  # 位置1为FileSystemEvent
FILTER_FUNC: TypeAlias = Callable[[FileSystemEvent], bool]  # 位置1为FileSystemEvent
observer = Observer()


def debounce(wait):
    """
    防抖函数
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            nonlocal last_call_time
            current_time = time.time()
            if (current_time - last_call_time) > wait:
                last_call_time = current_time
                return func(*args, **kwargs)

        last_call_time = None
        return wrapper

    return decorator


if get_config_with_compat("liteyuki.reload", ("dev_mode",), False):
    logger.debug("Liteyuki Reload enabled, watching for file changes...")
    observer.start()


class CodeModifiedHandler(FileSystemEventHandler):
    """
    Handler for code file changes
    """

    @debounce(1)
    def on_modified(self, event):
        raise NotImplementedError("on_modified must be implemented")

    def on_created(self, event):
        self.on_modified(event)

    def on_deleted(self, event):
        self.on_modified(event)

    def on_moved(self, event):
        self.on_modified(event)

    def on_any_event(self, event):
        self.on_modified(event)


def on_file_system_event(directories: tuple[str], recursive: bool = True, event_filter: FILTER_FUNC = None) -> Callable[[CALLBACK_FUNC], CALLBACK_FUNC]:
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

            if event_filter is not None and not event_filter(event):
                return
            func(event)

        code_modified_handler = CodeModifiedHandler()
        code_modified_handler.on_modified = wrapper
        for directory in directories:
            observer.schedule(code_modified_handler, directory, recursive=recursive)

        return func

    return decorator
