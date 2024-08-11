import multiprocessing

from .manager import *

__all__ = [
        "IS_MAIN_PROCESS"
]

IS_MAIN_PROCESS = multiprocessing.current_process().name == "MainProcess"

