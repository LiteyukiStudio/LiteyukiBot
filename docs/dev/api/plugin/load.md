---
title: liteyuki.plugin.load
order: 1
icon: laptop-code
category: API
---

### ***def*** `load_plugin(module_path: str | Path) -> Optional[Plugin]`

加载单个插件，可以是本地插件或是通过 `pip` 安装的插件。



参数:

    module_path: 插件名称 `path.to.your.plugin`

    或插件路径 `pathlib.Path(path/to/your/plugin)`

### ***def*** `load_plugins() -> set[Plugin]`

导入文件夹下多个插件



参数:

    plugin_dir: 文件夹路径

    ignore_warning: 是否忽略警告，通常是目录不存在或目录为空

### ***def*** `format_display_name(display_name: str, plugin_type: PluginType) -> str`

设置插件名称颜色，根据不同类型插件设置颜色

Args:

    display_name: 插件名称

    plugin_type: 插件类型



Returns:

    str: 设置后的插件名称 <y>name</y>

### ***var*** `module_path = path_to_module_name(Path(module_path)) if isinstance(module_path, Path) else module_path`



### ***var*** `plugins = set()`



### ***var*** `color = 'y'`



### ***var*** `module = import_module(module_path)`



### ***var*** `display_name = module.__name__.split('.')[-1]`



### ***var*** `display_name = format_display_name(f"{metadata.name}({module.__name__.split('.')[-1]})", metadata.type)`



### ***var*** `path = Path(os.path.join(dir_path, f))`



### ***var*** `module_name = None`



### ***var*** `color = 'm'`



### ***var*** `color = 'g'`



### ***var*** `color = 'e'`



### ***var*** `color = 'c'`



### ***var*** `module_name = f'{path_to_module_name(Path(dir_path))}.{f[:-3]}'`



### ***var*** `module_name = path_to_module_name(path)`



