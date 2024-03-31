---
title: 基础命令
icon: comment
order: 1
category: 使用手册
---

## 基础插件命令

#### 命令前有[S]的表示仅超级用户可用，[O]和[A]分别为群主和群管可用

### 轻雪`liteyuki`

```shell
[S]reload-liteyuki  # 重载轻雪
[S]update-liteyuki  # 更新轻雪
[S]liteyuki # 查看轻雪信息
[S]config set <key> value  # 添加配置项，若存在则会覆盖，输入值会被执行，以便于转换为正确的值，"10"和10是不一样的
[S]config get [key]  # 查询配置项，不带key返回配置项列表，推荐私聊使用
# 上述两个命令修改的配置项在数据库中保存，但是优先级低于配置文件，如果配置文件中存在相同的配置项，将会使用配置文件中的配置
------
别名: reload-liteyuki 重启轻雪, update-liteyuki 更新轻雪, config 配置， set 设置， get 查询
```

### 轻雪Nonebot插件管理 `liteyuki_npm`

```shell
[S]npm update  # 更新插件索引
[S]npm install <plugin_name>  # 安装插件
[S]npm uninstall <plugin_name>  # 卸载插件
[S]npm search <keywords...>  # 通过关键词搜索插件
------
别名: npm 插件, update 更新, install 安装, uninstall 卸载, search 搜索
```

```shell
[SOA]enable <plugin_name>  # 启用插件
[SOA]disable <plugin_name>  # 禁用插件
[S]enable-global <plugin_name>  # 全局启用插件
[S]disable-global <plugin_name>  # 全局禁用插件
list-plugin # 列出所有插件
# 受限于Nonebot的钩子函数，目前只能阻断消息事件的传入，对于主动推送消息的插件，无法将其阻止
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

**参数**：`<param>`为必填参数，`[option]`为可选参数。

**命令别名**：配置了命令别名的命令可以使用别名代替原命令，例如`npm install ~`可以使用`插件 安装 ~`代替。
