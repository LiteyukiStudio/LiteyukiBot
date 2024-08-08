# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/7 下午10:40
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : lib_loader.py
@Software: PyCharm
"""
import os
import sys
import platform
import ctypes

LIB_EXT = None
PLATFORM = platform.system().lower()  # linux, windows, darwin etc
ARCH = platform.machine().lower()  # x86_64/amd64 i386 i686 arm aarch64 ppc64 ppc mips sparc

if "linux" in PLATFORM:
    LIB_EXT = 'so'
elif sys.platform == 'darwin':
    LIB_EXT = 'dylib'
elif sys.platform == 'win32':
    LIB_EXT = 'dll'
else:
    raise RuntimeError("Unsupported platform")


def load_lib(lib_name: str) -> ctypes.CDLL:
    """
    Load a dll/so/dylib library, without extension.
    Args:
        lib_name: str, path/to/library without extension
    Returns:
        xxx_{platform}_{arch}.{ext} ctypes.CDLL
    """
    whole_path = f"{lib_name}_{PLATFORM}_{ARCH}.{LIB_EXT}"
    if not os.path.exists(whole_path):
        raise FileNotFoundError(f"Library {whole_path} not found")
    return ctypes.CDLL(whole_path)
