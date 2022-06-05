## Liteyuki Bot 使用手册

### 开始

- 使用`help`、`菜单`命令查看插件列表
- 使用`help <插件名/插件id>`查看单个插件的使用文档，例如`help 自动回复`
- 使用`help <插件名/插件id> <子文档>`查看插件的子文档，例如`help 学科工具 语文`
- 提示：命令参数中的`<>`表示此参数为必填，`[]`表示可选，实际输入命令无需带括号

### 安装插件

- 直接在cmd命令行使用`nb plugin install <插件名>`命令安装

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

- `manifest.json`中填写内容如下，`name`是插件名，最好是唯一的，可以自定义，便于插件管理

```json
{
    "name": "NoneBot示例插件"
}
```

- `docs.txt`中就是插件文档，可以从github项目的README.md复制，也可以自己编写，这是给QQ用户呈现的，
  若帮助文档是图片，则可以填写图片CQ码`[CQ:image,file=图片链接/路径

- 此时给你的Bot发送`help`，返回的插件列表应该就有你新装的插件了