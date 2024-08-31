---
title: 答疑
order: 3
---
# 答疑
## **常见问题**

- 设备上Python环境太乱了，pip和python不对应怎么办？
    - 请使用`/path/to/python -m pip install -r requirements.txt`来安装依赖，
      然后用`/path/to/python main.py`来启动Bot，
      其中`/path/to/python`是你要用来运行Bot的可执行文件

- 为什么我启动后机器人没有反应？
    - 请检查配置文件的`command_start`或`superusers`，确认你有权限使用命令并按照正确的命令发送
    - 确认命令头没有和`nickname{}`冲突，例如一个命令是`help`，但是`Bot`昵称有一个`help`，那么将会被解析为nickname而不是命令

- 更新轻雪失败，报错`InvalidGitRepositoryError`
    - 请正确安装`Git`，并使用克隆而非直接下载的方式部署轻雪

- 怎么登录聊天平台，例如QQ？
    - 你有这个问题说明你不是很了解这个项目，本项目不负责实现登录功能，只负责处理和回应消息，登录功能由实现端（协议端）提供，
      实现端本身不负责处理响应逻辑，将消息按照OneBot标准处理好上报给轻雪
      你需要使用Onebot标准的实现端来连接到轻雪并将消息上报给轻雪，下面已经列出一些推荐的实现端
- `Playwright`安装失败
    - 输入`playwright install`安装浏览器
- 有的插件安装后报错无法启动
    - 请先查阅插件文档，确认插件必要配置项完好后，仍然出现问题，请联系插件作者或在安全模式`safe_mode: true`下启动轻雪，在安全模式下你可以使用`npm uninstall`卸载问题插件
- 其他问题
    -
    加入QQ群[775840726](http://qm.qq.com/cgi-bin/qm/qr?_wv=1027&k=SzmDYbfR6jY94o9KFNon7AwelRyI6M_u&authKey=ygeBdEmdFNyCWuNR4w0M1M8%2B5oDg7k%2FDfN0tzBkYcnbB%2FGHNnlVEnCIGbdftsnn7&noverify=0&group_code=775840726)

## **推荐方案(QQ)**

1. [Lagrange.OneBot](https://github.com/KonataDev/Lagrange.Core)，基于NTQQ的OneBot实现，目前Markdown消息支持Lagrange
2. [LLOneBot](https://github.com/LLOneBot/LLOneBot)，NTQQ的OneBot插件，需要安装NTQQ
3. [OpenShamrock](https://github.com/whitechi73/OpenShamrock)，基于Lsposed的OneBot11实现
4. [TRSS-Yunzai](https://github.com/TimeRainStarSky/Yunzai)，基于`node.js`，可使用`ws-plugin`进行通信
5. [go-cqhttp](https://github.com/Mrs4s/go-cqhttp)，`go`语言实现的OneBot11实现端，目前可用性较低
6. [Gensokyo](https://github.com/Hoshinonyaruko/Gensokyo)，基于 OneBot QQ官方机器人Api Golang 原生实现，需要官方机器人权限
7. 人工实现的`Onebot`协议，自己整一个WebSocket客户端，看着QQ的消息，然后给轻雪传输数据

## **推荐方案(Minecraft)**

1. [MinecraftOneBot](https://github.com/snowykami/MinecraftOnebot)，我们专门为Minecraft开发的服务器Bot，支持OneBotV11标准

使用其他项目连接请先自行查阅文档，若有困难请联系对应开发者而不是Liteyuki的开发者

## **鸣谢**

- [Nonebot2](https://nonebot.dev)提供的框架支持
- [nonebot-plugin-alconna](https://github.com/ArcletProject/nonebot-plugin-alconna)提供的命令解析功能
- [MiSans](https://hyperos.mi.com/font/zh/)，[MapleMono](https://gitee.com/mirrors/Maple-Mono)提供的字体，且遵守了相关字体开源协议
