import time

import nonebot
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from liteyuki.utils.base.config import get_config
from liteyuki.utils.base.reloader import Reloader
from liteyuki.utils.base.resource import load_resources

if get_config("liteyuki_reload", False):
    nonebot.logger.info("Liteyuki Reload is enable, watching for file changes...")


    class CodeModifiedHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if "liteyuki/resources" not in event.src_path.replace("\\", "/"):
                nonebot.logger.debug(f"{event.src_path} has been modified, reloading bot...")
                Reloader.reload()


    class ResourceModifiedHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if not event.is_directory:
                nonebot.logger.debug(f"{event.src_path} has been modified, reloading resource...")
                load_resources()


    code_modified_handler = CodeModifiedHandler()
    resource_modified_handle = ResourceModifiedHandler()

    observer = Observer()
    observer.schedule(resource_modified_handle, path="liteyuki/resources", recursive=True)
    observer.schedule(resource_modified_handle, path="resources", recursive=True)
    observer.schedule(code_modified_handler, path="liteyuki", recursive=True)
    observer.start()

# try:
#     while True:
#         time.sleep(1)
# except KeyboardInterrupt:
#     observer.stop()
# observer.join()
