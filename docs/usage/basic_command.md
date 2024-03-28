---
title: 基础命令
icon: laptop-code
order: 1
category: 使用手册
---


## 内置插件命令

### 轻雪`liteyuki`

```shell
reload-liteyuki  # 重载轻雪
update-liteyuki  # 更新轻雪
liteyuki # 查看轻雪信息
```

### 轻雪Nonebot插件管理 `liteyuki_npm`

```shell
npm update  # 更新插件索引
npm install <plugin_name>  # 安装插件
npm uninstall <plugin_name>  # 卸载插件
npm search <keywords...>  # 搜索插件
------
别名: npm 插件, update 更新, install 安装, uninstall 卸载, search 搜索
```

```shell
enable <plugin_name>  # 启用插件
disable <plugin_name>  # 禁用插件
enable-global <plugin_name>  # 全局启用插件
disable-global <plugin_name>  # 全局禁用插件
list-plugin # 列出所有插件
------
别名: enable 启用, disable 停用, enable-global 全局启用, disable-global 全局停用, list-plugin 列出插件/插件列表
```

### 轻雪用户管理`liteyuki_user`

```shell
profile  # 查看用户信息菜单
profile set <key> [value]  # 设置用户信息或打开属性设置菜单
profile get <key>  # 获取用户信息
------
别名: profile 个人信息, set 设置, get 查询
```

*参数：`<param>`为必填参数，`[param]`为可选参数。*

*命令别名：配置了命令别名的命令可以使用别名代替原命令，例如`npm install ~`可以使用`插件 安装 ~`代替。*