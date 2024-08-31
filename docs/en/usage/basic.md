---
title: 基础插件
order: 1
---

# 基础插件
---

> [!tip]
> **参数**：`<param>`为必填参数，`[option]`为可选参数。
>
> **命令别名**：配置了命令别名的命令可以使用别名代替原命令，例如`npm install ~`可以使用`插件 安装 ~`代替。

## **轻雪命令`liteyuki_command`**


|                    命令                    |                                              说明                                               |                    权限                    |                            举例                             |                                       可用参数                                       |
| :----------------------------------------: | :---------------------------------------------------------------------------------------------: | :----------------------------------------: | :---------------------------------------------------------: | :----------------------------------------------------------------------------------: |
|             `reload-liteyuki`              |                                            重载轻雪                                             |                  超级用户                  |                              ❌                              |                                          ❌                                           |
|             `update-liteyuki`              |                                            更新轻雪                                             |                  超级用户                  |                              ❌                              |                                          ❌                                           |
|                 `liteecho`                 |                                        查看当前bot 版本                                         |                  超级用户                  |                              ❌                              |                                          ❌                                           |
|                  `status`                  |                                       查看统计信息和状态                                        |                  超级用户                  |                              ❌                              |                                          ❌                                           |
|          `config set <key> value`          |        添加配置项，若存在则会覆盖，输入值会被执行以转换为正确的类型，"10"和10是不一样的         |                  超级用户                  |              `config set name 'liteyuki-bot'`               | `<key>`: 若存在则覆盖, 若不存在则创建于`config.yml` ; `value`: yml格式的所有合法内容 |
|            `config get [key] `             |                         查询配置项，不带key返回配置项列表，推荐私聊使用                         |                  超级用户                  |                      `config get name`                      |                       `<key>`: 若存在则返回, 若不存在则返回空                        |
|            `switch-image-mode `            | 在普通图片和Markdown大图之间切换，该功能需要commit:505468b及以后的Lagrange.OneBot，默认普通图片 |                  超级用户                  |                     `switch-image-mode`                     |                                          ❌                                           |
|          `/api api_name [args] `           |                                          调用机器人API                                          |                  超级用户                  |        `/api get_group_member_list group_id=1234567`        |             `<args>`: 参数列表, 格式为onebot v11协议api, 可用%20代替空格             |
| `/function function_name [args] [kwargs] ` |                                调用机器人函数(`.lyfunction`语法)                                |                  超级用户                  | `/function send_group_msg group_id=1234567 message='hello'` |              `<args>`和`<kwargs>`: 参数列表, api格式为onebot v11协议api              |
|      group enable/disable [group_id]       |                          在群聊启用/停用机器人，group_id仅超级用户可用                          | 超级用户，群聊仅群主、管理员、超级用户可用 |                `group enable 1145141919810`                 |                                  `<group_id>`: 群号                                  |
|               liteyuki-docs                |                                          查看轻雪文档                                           |                   所有人                   |                              ❌                              |                                          ❌                                           |


---
### **命令别名**


|       命令        |                 别名                 |
| :---------------: | :----------------------------------: |
|      status       |                 状态                 |
|  reload-liteyuki  |               重启轻雪               |
|  update-liteyuki  |               更新轻雪               |
| reload-resources  |               重载资源               |
|      config       |    配置, `set` 设置 / `get` 查询     |
| switch-image-mode |             切换图片模式             |
|   liteyuki-docs   |               轻雪文档               |
|       group       | 群聊, `enable` 启用 / `disable` 停用 |


---

## **插件/包管理器 `liteyuki_pacman`**

- 插件管理

|                          命令                           |                    说明                    |                       权限                       |
| :-----------------------------------------------------: | :----------------------------------------: | :----------------------------------------------: |
|                      `npm update`                       |              更新插件商店索引              |                     超级用户                     |
|               `npm install <plugin_name>`               |                  安装插件                  |                     超级用户                     |
|              `npm uninstall <plugin_name>`              |                  卸载插件                  |                     超级用户                     |
|               `npm search <keywords...>`                |             通过关键词搜索插件             |                     超级用户                     |
|    `npm enable-global/disable-global <plugin_name>`     |             全局启用/停用插件              |                     超级用户                     |
| `npm enable/disable <plugin_name> [--group <group_id>]` |           当前会话启用/停用插件            | 群聊仅群主、管理员、超级用户可用，私聊所有人可用 |
|                 `npm list [page] [num]`                 | 列出所有插件 page为页数，num为每页显示数量 | 群聊仅群主、管理员、超级用户可用，私聊所有人可用 |
|                  `help <plugin_name>`                   |                查看插件帮助                |                      所有人                      |


- 资源包管理

|           命令           |                     说明                     |   权限   |
| :----------------------: | :------------------------------------------: | :------: |
| `rpm list [page] [num]`  | 列出所有资源包 page为页数，num为每页显示数量 | 超级用户 |
|  `rpm load <pack_name>`  |                  加载资源包                  | 超级用户 |
| `rpm unload <pack_name>` |                  卸载资源包                  | 超级用户 |
| `rpm change <pack_name>` |                  修改优先级                  | 超级用户 |
|       `rpm reload`       |                重载所有资源包                | 超级用户 |


### 命令别名

|       命令       |   别名   |
| :--------------: | :------: |
|      `npm`       | 插件管理 |
|     `update`     |   更新   |
|    `install`     |   安装   |
|   `uninstall`    |   卸载   |
|     `search`     |   搜索   |
|     `enable`     |   启用   |
|    `disable`     |   停用   |
| `enable-global`  | 全局启用 |
| `disable-global` | 全局停用 |
|      `rpm`       |  资源包  |
|      `load`      |   加载   |
|     `unload`     |   卸载   |
|     `change`     |   更改   |
|     `reload`     |   重载   |
|      `list`      |   列表   |
|      `help`      |   帮助   |

> [!warning]
> 受限于NoneBot2钩子函数的依赖注入参数，插件停用只能阻断传入响应，对于主动推送的插件不生效，请阅读插件主页的说明。
> 

---


## **用户管理`liteyuki_user`**

|            命令             |              说明              |  权限  |
| :-------------------------: | :----------------------------: | :----: |
|          `profile`          |        查看用户信息菜单        | 所有人 |
| `profile set <key> [value]` | 设置用户信息或打开属性设置菜单 | 所有人 |
|     `profile get <key>`     |          获取用户信息          | 所有人 |


###命令别名

|   命令    |   别名   |
| :-------: | :------: |
| `profile` | 个人信息 |
|   `set`   |   设置   |
|   `get`   |   查询   |


