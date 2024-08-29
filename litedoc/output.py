# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/28 下午3:59
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : output.py
@Software: PyCharm
"""
import os.path

from litedoc.style.markdown import generate
from litedoc.syntax.astparser import AstParser


def write_to_file(content: str, output: str) -> None:
    """
    Write content to file.

    Args:
        content: str, content to write.
        output: str, path to output file.
    """
    if not os.path.exists(os.path.dirname(output)):
        os.makedirs(os.path.dirname(output))

    with open(output, "w", encoding="utf-8") as f:
        f.write(content)


def get_file_list(module_folder: str):
    file_list = []
    for root, dirs, files in os.walk(module_folder):
        for file in files:
            if file.endswith((".py", ".pyi")):
                file_list.append(os.path.join(root, file))
    return file_list


def get_relative_path(base_path: str, target_path: str) -> str:
    """
    获取相对路径
    Args:
        base_path: 基础路径
        target_path: 目标路径
    """
    return os.path.relpath(target_path, base_path)


def generate_from_module(module_folder: str,
                         output_dir: str,
                         with_top: bool = False,
                         lang: str = "zh-Hans",
                         ignored_paths=None,
                         theme: str = "vitepress",
                         style: str = "google"
                         ):
    """
    生成文档
    Args:
        module_folder: 模块文件夹
        output_dir: 输出文件夹
        with_top: 是否包含顶层文件夹 False时例如docs/api/module_a, docs/api/module_b， True时例如docs/api/module/module_a.md， docs/api/module/module_b.md
        ignored_paths: 忽略的路径
        lang: 语言
        theme: 主题
        style: 样式
    """
    if ignored_paths is None:
        ignored_paths = []
    file_data: dict[str, str] = {}  # 路径 -> 字串

    file_list = get_file_list(module_folder)

    # 清理输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    replace_data = {
            "__init__": "index" if theme == "vitepress" else "README",
            ".py"     : ".md",
    }

    for pyfile_path in file_list:
        if any(ignored_path.replace("\\", "/") in pyfile_path.replace("\\", "/") for ignored_path in ignored_paths):
            continue

        no_module_name_pyfile_path = get_relative_path(module_folder, pyfile_path)  # 去头路径

        # markdown相对路径
        rel_md_path = pyfile_path if with_top else no_module_name_pyfile_path
        for rk, rv in replace_data.items():
            rel_md_path = rel_md_path.replace(rk, rv)

        abs_md_path = os.path.join(output_dir, rel_md_path)

        # 获取模块信息
        ast_parser = AstParser(open(pyfile_path, "r", encoding="utf-8").read())

        # 生成markdown

        front_matter = {
                "title": pyfile_path.replace("\\", "/").
                replace("/", ".").
                replace(".py", "").
                replace(".__init__", ""),

        }

        md_content = generate(ast_parser, lang=lang, frontmatter=front_matter)
        print(f"Generate {pyfile_path} -> {abs_md_path}")
        file_data[abs_md_path] = md_content

    for fn, content in file_data.items():
        write_to_file(content, fn)
