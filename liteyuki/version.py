# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/18 上午3:49
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : version.py.py
@Software: PyCharm
"""
from git import Repo
from pdm.backend.hooks.version import SCMVersion

try:
    __commit__ = Repo(".").head.commit.hexsha
except:
    __commit__ = "unknown"

__version__ = "6.3.5"


def format_version(version: SCMVersion) -> str:
    return f"{__version__}+{__commit__[:7]}"
