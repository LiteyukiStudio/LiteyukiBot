# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/11 下午10:01
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : observer.py
@Software: PyCharm
"""
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from liteyuki import get_config, logger, get_bot

liteyuki_bot = get_bot()

if get_config("debug", False):

    src_directories = (
            "src/nonebot_plugins",
            "src/utils",
    )
    src_excludes_extensions = (
            "pyc",
    )
    logger.debug("Liteyuki Reload enabled, watching for file changes...")

    class CodeModifiedHandler(FileSystemEventHandler):
        """
        Handler for code file changes
        """
        def on_modified(self, event):
            if event.src_path.endswith(
                    src_excludes_extensions) or event.is_directory or "__pycache__" in event.src_path:
                return
            logger.info(f"{event.src_path} modified, reloading bot...")
            liteyuki_bot.restart_process("nonebot")

    code_modified_handler = CodeModifiedHandler()

    observer = Observer()
    for directory in src_directories:
        observer.schedule(code_modified_handler, directory, recursive=True)
    observer.start()