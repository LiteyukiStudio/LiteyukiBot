## Liteyuki Bot 使用手册

### 开始

- 使用`help`、`菜单`命令查看插件列表
- 使用`help <插件名/插件id>`查看单个插件的使用文档，例如`help 自动回复`
- 使用`help <插件名/插件id> <子文档>`查看插件的子文档，例如`help 学科工具 语文`
- 提示：命令参数中的`<>`表示此参数为必填，`[]`表示可选，实际输入命令无需带括号

### 安装插件

- 直接在cmd命令行使用`nb plugin install <插件名>`命令安装（此方法安装的插件不支持轻雪插件管理，可以使用nonebot插件商店中的插件管理代替，
  但是效率没有自建Rule高）

- 支持插件管理（但较复杂，大概会花费3分钟配置插件）：Bot在首次运行时会生成`src/nonebot_plugin`文件夹，
  将含有`__init__.py`的插件文件夹拖放到此处，
  并在插件文件夹内创建`config`文件夹，在`config`内创建`manifest.json`和`docs.txt`,其目录结构如下

```
Liteyuki-Bot
├── bot.py
├── README.md
├── ...
└── src
    ├── extraApi
    ├── liteyuki-built-in
    └── nonebot_plugin
        └── example_plugin
            ├── __init__.py
            ├── ...
            └── config
                ├── docs.txt
                └── manifest.json
```

- `manifest.json`中填写内容如下，其中`id`是插件id，每个插件都是唯一的，可以自定义，建议`nb.作者名.插件名`，
  `name`是插件名，最好是唯一的，可以自定义，便于插件管理

```json
{
    "id": "nb.example_plugin",
    "name": "NoneBot示例插件"
}
```

- `docs.txt`中就是插件文档，可以从github项目的README.md复制，也可以自己编写，这是给QQ用户呈现的，
  若帮助文档是图片，则可以填写图片CQ码`[CQ:image,file=图片链接/路径]`
- 编写插件代码，这一步如果你没有基础就不要操作了，可以把插件发给Liteyuki Bot作者帮你改
  轻雪插件管理的实现原理是自建Rule，也是侵入式管理。

```python
# 从外部api导入这四个Ru
from nonebot import on_command
from ...extraApi.rule import plugin_enable, MODE_DETECT, NOT_IGNORED, NOT_BLOCKED
plugin_id = "nb.example"
PLUGIN_ENABLE = plugin_enable(plugin_id)    # 此函数不是Rule，但是会返回一个Rule(async func)
# 寻找到所有匹配器，此处举例，将四个Rule添加到
matcher_1 = on_command(cmd="example", rule=PLUGIN_ENABLE & MODE_DETECT & NOT_IGNORED & NOT_BLOCKED)
matcher_2 = on_command(cmd="example2", rule=PLUGIN_ENABLE & MODE_DETECT & NOT_IGNORED & NOT_BLOCKED)
...
```

- 此时给你的Bot发送`help`，返回的插件列表应该就有你新装的插件了