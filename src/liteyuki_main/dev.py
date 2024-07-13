import nonebot
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.utils.base.config import get_config
from src.utils.base.reloader import Reloader
from src.utils.base.resource import load_resources

if get_config("debug", False):

    src_directories = (
        "src/liteyuki_main",
        "src/plugins",
        "src/utils",
    )
    src_excludes_extensions = (
        "pyc",
    )

    res_directories = (
        "src/resources",
        "resources",
    )

    nonebot.logger.info("Liteyuki Reload enabled, watching for file changes...")


    class CodeModifiedHandler(FileSystemEventHandler):
        """
        Handler for code file changes
        """

        def on_modified(self, event):
            if event.src_path.endswith(
                    src_excludes_extensions) or event.is_directory or "__pycache__" in event.src_path:
                return
            nonebot.logger.info(f"{event.src_path} modified, reloading bot...")
            Reloader.reload()


    class ResourceModifiedHandler(FileSystemEventHandler):
        """
        Handler for resource file changes
        """

        def on_modified(self, event):
            nonebot.logger.info(f"{event.src_path} modified, reloading resource...")
            load_resources()


    code_modified_handler = CodeModifiedHandler()
    resource_modified_handle = ResourceModifiedHandler()

    observer = Observer()
    for directory in src_directories:
        observer.schedule(code_modified_handler, directory, recursive=True)
    for directory in res_directories:
        observer.schedule(resource_modified_handle, directory, recursive=True)
    observer.start()
