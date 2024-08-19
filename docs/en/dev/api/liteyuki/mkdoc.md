---
title: liteyuki.mkdoc
order: 1
icon: laptop-code
category: API
---

### ***def*** `get_relative_path(base_path: str, target_path: str) -> str`

获取相对路径

Args:

    base_path: 基础路径

    target_path: 目标路径

### ***def*** `write_to_files(file_data: dict[str, str]) -> None`

输出文件

Args:

    file_data: 文件数据 相对路径

### ***def*** `get_file_list(module_folder: str) -> None`



### ***def*** `get_module_info_normal(file_path: str, ignore_private: bool) -> ModuleInfo`

获取函数和类

Args:

    file_path: Python 文件路径

    ignore_private: 忽略私有函数和类

Returns:

    模块信息

### ***def*** `generate_markdown(module_info: ModuleInfo, front_matter: Any) -> str`

生成模块的Markdown

你可在此自定义生成的Markdown格式

Args:

    module_info: 模块信息

    front_matter: 自定义选项title, index, icon, category

Returns:

    Markdown 字符串

### ***def*** `generate_docs(module_folder: str, output_dir: str, with_top: bool, ignored_paths: Any) -> None`

生成文档

Args:

    module_folder: 模块文件夹

    output_dir: 输出文件夹

    with_top: 是否包含顶层文件夹 False时例如docs/api/module_a, docs/api/module_b， True时例如docs/api/module/module_a.md， docs/api/module/module_b.md

    ignored_paths: 忽略的路径

### ***class*** `DefType(Enum)`



### &emsp; ***attr*** `FUNCTION: 'function'`

### &emsp; ***attr*** `METHOD: 'method'`

### &emsp; ***attr*** `STATIC_METHOD: 'staticmethod'`

### &emsp; ***attr*** `CLASS_METHOD: 'classmethod'`

### &emsp; ***attr*** `PROPERTY: 'property'`

### ***class*** `FunctionInfo(BaseModel)`



### ***class*** `AttributeInfo(BaseModel)`



### ***class*** `ClassInfo(BaseModel)`



### ***class*** `ModuleInfo(BaseModel)`



### ***var*** `NO_TYPE_ANY = 'Any'`



### ***var*** `NO_TYPE_HINT = 'NoTypeHint'`



### ***var*** `FUNCTION = 'function'`



### ***var*** `METHOD = 'method'`



### ***var*** `STATIC_METHOD = 'staticmethod'`



### ***var*** `CLASS_METHOD = 'classmethod'`



### ***var*** `PROPERTY = 'property'`



### ***var*** `file_list = []`



### ***var*** `dot_sep_module_path = file_path.replace(os.sep, '.').replace('.py', '').replace('.pyi', '')`



### ***var*** `module_docstring = ast.get_docstring(tree)`



### ***var*** `module_info = ModuleInfo(module_path=dot_sep_module_path, functions=[], classes=[], attributes=[], docstring=module_docstring if module_docstring else '')`



### ***var*** `content = ''`



### ***var*** `front_matter = '---\n' + '\n'.join([f'{k}: {v}' for k, v in front_matter.items()]) + '\n---\n\n'`



### ***var*** `file_list = get_file_list(module_folder)`



### ***var*** `replace_data = {'__init__': 'README', '.py': '.md'}`



### ***var*** `file_content = file.read()`



### ***var*** `tree = ast.parse(file_content)`



### ***var*** `args_with_type = [f'{arg[0]}: {arg[1]}' if arg[1] else arg[0] for arg in func.args]`



### ***var*** `ignored_paths = []`



### ***var*** `no_module_name_pyfile_path = get_relative_path(module_folder, pyfile_path)`



### ***var*** `rel_md_path = pyfile_path if with_top else no_module_name_pyfile_path`



### ***var*** `abs_md_path = os.path.join(output_dir, rel_md_path)`



### ***var*** `module_info = get_module_info_normal(pyfile_path)`



### ***var*** `md_content = generate_markdown(module_info, front_matter)`



### ***var*** `inherit = f"({', '.join(cls.inherit)})" if cls.inherit else ''`



### ***var*** `rel_md_path = rel_md_path.replace(rk, rv)`



### ***var*** `front_matter = {'title': module_info.module_path.replace('.__init__', '').replace('_', '\\n'), 'index': 'true', 'icon': 'laptop-code', 'category': 'API'}`



### ***var*** `front_matter = {'title': module_info.module_path.replace('_', '\\n'), 'order': '1', 'icon': 'laptop-code', 'category': 'API'}`



### ***var*** `function_docstring = ast.get_docstring(node)`



### ***var*** `func_info = FunctionInfo(name=node.name, args=[(arg.arg, ast.unparse(arg.annotation) if arg.annotation else NO_TYPE_ANY) for arg in node.args.args], return_type=ast.unparse(node.returns) if node.returns else 'None', docstring=function_docstring if function_docstring else '', type=DefType.FUNCTION, is_async=isinstance(node, ast.AsyncFunctionDef))`



### ***var*** `class_docstring = ast.get_docstring(node)`



### ***var*** `class_info = ClassInfo(name=node.name, docstring=class_docstring if class_docstring else '', methods=[], attributes=[], inherit=[ast.unparse(base) for base in node.bases])`



### ***var*** `args_with_type = [f'{arg[0]}: {arg[1]}' if arg[1] else arg[0] for arg in method.args]`



### ***var*** `args_with_type = [f'{arg[0]}: {arg[1]}' if arg[1] and arg[0] != 'self' else arg[0] for arg in method.args]`



### ***var*** `first_arg = node.args.args[0]`



### ***var*** `method_docstring = ast.get_docstring(class_node)`



### ***var*** `def_type = DefType.METHOD`



### ***var*** `def_type = DefType.STATIC_METHOD`



### ***var*** `attr_type = NO_TYPE_HINT`



### ***var*** `def_type = DefType.CLASS_METHOD`



### ***var*** `attr_type = ast.unparse(node.value.annotation)`



### ***var*** `def_type = DefType.PROPERTY`



