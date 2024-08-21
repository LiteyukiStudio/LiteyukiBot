# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 上午6:23
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : mkdoc.py
@Software: PyCharm
"""

import ast
import os
import shutil
from typing import Any
from enum import Enum
from pydantic import BaseModel

NO_TYPE_ANY = "Any"
NO_TYPE_HINT = "NoTypeHint"


class DefType(Enum):
    FUNCTION = "function"
    METHOD = "method"
    STATIC_METHOD = "staticmethod"
    CLASS_METHOD = "classmethod"
    PROPERTY = "property"


class FunctionInfo(BaseModel):
    name: str
    args: list[tuple[str, str]]
    return_type: str
    docstring: str
    source_code: str = ""

    type: DefType
    """若为类中def，则有"""
    is_async: bool


class AttributeInfo(BaseModel):
    name: str
    type: str
    value: Any = None
    docstring: str = ""


class ClassInfo(BaseModel):
    name: str
    docstring: str
    methods: list[FunctionInfo]
    attributes: list[AttributeInfo]
    inherit: list[str]


class ModuleInfo(BaseModel):
    module_path: str
    """点分割模块路径 例如 liteyuki.bot"""

    functions: list[FunctionInfo]
    classes: list[ClassInfo]
    attributes: list[AttributeInfo]
    docstring: str


def get_relative_path(base_path: str, target_path: str) -> str:
    """
    获取相对路径
    Args:
        base_path: 基础路径
        target_path: 目标路径
    """
    return os.path.relpath(target_path, base_path)


def write_to_files(file_data: dict[str, str]):
    """
    输出文件
    Args:
        file_data: 文件数据 相对路径
    """

    for rp, data in file_data.items():

        if not os.path.exists(os.path.dirname(rp)):
            os.makedirs(os.path.dirname(rp))
        with open(rp, 'w', encoding='utf-8') as f:
            f.write(data)


def get_file_list(module_folder: str):
    file_list = []
    for root, dirs, files in os.walk(module_folder):
        for file in files:
            if file.endswith((".py", ".pyi")):
                file_list.append(os.path.join(root, file))
    return file_list


def get_module_info_normal(file_path: str, ignore_private: bool = True) -> ModuleInfo:
    """
    获取函数和类
    Args:
        file_path: Python 文件路径
        ignore_private: 忽略私有函数和类
    Returns:
        模块信息
    """

    with open(file_path, 'r', encoding='utf-8') as file:
        file_content = file.read()
        tree = ast.parse(file_content)

    dot_sep_module_path = file_path.replace(os.sep, '.').replace(".py", "").replace(".pyi", "")
    module_docstring = ast.get_docstring(tree)

    module_info = ModuleInfo(
        module_path=dot_sep_module_path,
        functions=[],
        classes=[],
        attributes=[],
        docstring=module_docstring if module_docstring else ""
    )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # 模块函数 且不在类中 若ignore_private=True则忽略私有函数
            if not any(isinstance(parent, ast.ClassDef) for parent in ast.iter_child_nodes(node)) and (not ignore_private or not node.name.startswith('_')):

                # 判断第一个参数是否为self或cls，后期用其他办法优化
                if node.args.args:
                    first_arg = node.args.args[0]
                    if first_arg.arg in ("self", "cls"):
                        continue

                function_docstring = ast.get_docstring(node)

                func_info = FunctionInfo(
                    name=node.name,
                    args=[(arg.arg, ast.unparse(arg.annotation) if arg.annotation else NO_TYPE_ANY) for arg in node.args.args],
                    return_type=ast.unparse(node.returns) if node.returns else "None",
                    docstring=function_docstring if function_docstring else "",
                    type=DefType.FUNCTION,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    source_code=ast.unparse(node)
                )
                module_info.functions.append(func_info)

        elif isinstance(node, ast.ClassDef):
            # 模块类
            class_docstring = ast.get_docstring(node)

            class_info = ClassInfo(
                name=node.name,
                docstring=class_docstring if class_docstring else "",
                methods=[],
                attributes=[],
                inherit=[ast.unparse(base) for base in node.bases]
            )

            for class_node in node.body:
                # methods [instance, static, class， property]，保留__init__方法
                if isinstance(class_node, ast.FunctionDef) and (not ignore_private or not class_node.name.startswith('_') or class_node.name == "__init__"):
                    method_docstring = ast.get_docstring(class_node)
                    def_type = DefType.METHOD
                    if class_node.decorator_list:
                        if any(isinstance(decorator, ast.Name) and decorator.id == "staticmethod" for decorator in class_node.decorator_list):
                            def_type = DefType.STATIC_METHOD
                        elif any(isinstance(decorator, ast.Name) and decorator.id == "classmethod" for decorator in class_node.decorator_list):
                            def_type = DefType.CLASS_METHOD
                        elif any(isinstance(decorator, ast.Name) and decorator.id == "property" for decorator in class_node.decorator_list):
                            def_type = DefType.PROPERTY
                    class_info.methods.append(FunctionInfo(
                        name=class_node.name,
                        args=[(arg.arg, ast.unparse(arg.annotation) if arg.annotation else NO_TYPE_ANY) for arg in class_node.args.args],
                        return_type=ast.unparse(class_node.returns) if class_node.returns else "None",
                        docstring=method_docstring if method_docstring else "",
                        type=def_type,
                        is_async=isinstance(class_node, ast.AsyncFunctionDef),
                        source_code=ast.unparse(class_node)
                    ))
                # attributes
                elif isinstance(class_node, ast.Assign):
                    for target in class_node.targets:
                        if isinstance(target, ast.Name):
                            class_info.attributes.append(AttributeInfo(
                                name=target.id,
                                type=ast.unparse(class_node.value)
                            ))
            module_info.classes.append(class_info)

        elif isinstance(node, ast.Assign):
            # 检查是否在类或函数中
            if not any(isinstance(parent, (ast.ClassDef, ast.FunctionDef)) for parent in ast.iter_child_nodes(node)):
                # 模块属性变量
                for target in node.targets:
                    if isinstance(target, ast.Name) and (not ignore_private or not target.id.startswith('_')):
                        attr_type = NO_TYPE_HINT
                        if isinstance(node.value, ast.AnnAssign) and node.value.annotation:
                            attr_type = ast.unparse(node.value.annotation)
                        module_info.attributes.append(AttributeInfo(
                            name=target.id,
                            type=attr_type,
                            value=ast.unparse(node.value) if node.value else None
                        ))

    return module_info


def generate_markdown(module_info: ModuleInfo, front_matter=None, lang: str = "zh-CN") -> str:
    """
    生成模块的Markdown
    你可在此自定义生成的Markdown格式
    Args:
        module_info: 模块信息
        front_matter: 自定义选项title, index, icon, category
        lang: 语言
    Returns:
        Markdown 字符串
    """

    content = ""

    front_matter = "---\n" + "\n".join([f"{k}: {v}" for k, v in front_matter.items()]) + "\n---\n\n"

    content += front_matter

    # 模块函数
    for func in module_info.functions:
        args_with_type = [f"{arg[0]}: {arg[1]}" if arg[1] else arg[0] for arg in func.args]
        content += f"### ***{'async ' if func.is_async else ''}def*** `{func.name}({', '.join(args_with_type)}) -> {func.return_type}`\n\n"

        func.docstring = func.docstring.replace("\n", "\n\n")
        content += f"{func.docstring}\n\n"

        # 函数源代码可展开区域
        content += f"<details>\n<summary>源代码</summary>\n\n```python\n{func.source_code}\n```\n</details>\n\n"

    # 类
    for cls in module_info.classes:
        if cls.inherit:
            inherit = f"({', '.join(cls.inherit)})" if cls.inherit else ""
            content += f"### ***class*** `{cls.name}{inherit}`\n\n"
        else:
            content += f"### ***class*** `{cls.name}`\n\n"

        cls.docstring = cls.docstring.replace("\n", "\n\n")
        content += f"{cls.docstring}\n\n"
        for method in cls.methods:
            # 类函数

            if method.type != DefType.METHOD:
                args_with_type = [f"{arg[0]}: {arg[1]}" if arg[1] else arg[0] for arg in method.args]
                content += f"### &emsp; ***@{method.type.value}***\n"
            else:
                # self不加类型提示
                args_with_type = [f"{arg[0]}: {arg[1]}" if arg[1] and arg[0] != "self" else arg[0] for arg in method.args]
            content += f"### &emsp; ***{'async ' if method.is_async else ''}def*** `{method.name}({', '.join(args_with_type)}) -> {method.return_type}`\n\n"

            method.docstring = method.docstring.replace("\n", "\n\n")
            content += f"&emsp;{method.docstring}\n\n"
            # 函数源代码可展开区域

            if lang == "zh-CN":
                TEXT_SOURCE_CODE = "源代码"
            else:
                TEXT_SOURCE_CODE = "Source Code"

            content += f"<details>\n<summary>{TEXT_SOURCE_CODE}</summary>\n\n```python\n{method.source_code}\n```\n</details>\n\n"
        for attr in cls.attributes:
            content += f"### &emsp; ***attr*** `{attr.name}: {attr.type}`\n\n"

    # 模块属性
    for attr in module_info.attributes:
        if attr.type == NO_TYPE_HINT:
            content += f"### ***var*** `{attr.name} = {attr.value}`\n\n"
        else:
            content += f"### ***var*** `{attr.name}: {attr.type} = {attr.value}`\n\n"

        attr.docstring = attr.docstring.replace("\n", "\n\n")
        content += f"{attr.docstring}\n\n"

    return content


def generate_docs(module_folder: str, output_dir: str, with_top: bool = False, lang: str = "zh-CN", ignored_paths=None):
    """
    生成文档
    Args:
        module_folder: 模块文件夹
        output_dir: 输出文件夹
        with_top: 是否包含顶层文件夹 False时例如docs/api/module_a, docs/api/module_b， True时例如docs/api/module/module_a.md， docs/api/module/module_b.md
        ignored_paths: 忽略的路径
        lang: 语言
    """
    if ignored_paths is None:
        ignored_paths = []
    file_data: dict[str, str] = {}  # 路径 -> 字串

    file_list = get_file_list(module_folder)

    # 清理输出目录
    shutil.rmtree(output_dir, ignore_errors=True)
    os.mkdir(output_dir)

    replace_data = {
            "__init__": "README",
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
        module_info = get_module_info_normal(pyfile_path)

        # 生成markdown

        if "README" in abs_md_path:
            front_matter = {
                    "title"   : module_info.module_path.replace(".__init__", "").replace("_", "\\n"),
                    "index"   : "true",
                    "icon"    : "laptop-code",
                    "category": "API"
            }
        else:
            front_matter = {
                    "title"   : module_info.module_path.replace("_", "\\n"),
                    "order"   : "1",
                    "icon"    : "laptop-code",
                    "category": "API"
            }

        md_content = generate_markdown(module_info, front_matter)
        print(f"Generate {pyfile_path} -> {abs_md_path}")
        file_data[abs_md_path] = md_content

    write_to_files(file_data)


# 入口脚本
if __name__ == '__main__':
    # 这里填入你的模块路径
    generate_docs('liteyuki', 'docs/dev/api', with_top=False, ignored_paths=["liteyuki/plugins"], lang="zh-CN")
    generate_docs('liteyuki', 'docs/en/dev/api', with_top=False, ignored_paths=["liteyuki/plugins"], lang="en")
