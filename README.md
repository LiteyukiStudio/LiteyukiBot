<div align="center">

![图片](/docs/img/luxun.png)

# Liteyuki Bot


### 轻雪机器人

#### 基于[Nonebot](https://v2.nonebot.dev/)库的QQ机器人

</div>

## 简介

作者没有女朋友那段时间一个人过于寂寞，便写了这个bot来陪伴自己，顺便学习一些相关知识。使用了Nonebot库，继承了Nonebot的大部分优点，作者自己造了很多轮子和~~屎山~~。有相对简洁的插件管理功能。代码很烂，自己用的。

## 安装

#### 1.安装Python3.10运行环境

###### Windows

- 机器人是需要Python运行环境的
- 转到[下载页面](https://www.python.org/downloads/release/python-3100/)，选择你需要的版本下载，记得勾选`Add Python to environment variables`
- 不会请看[这里](https://zhuanlan.zhihu.com/p/344887837)

###### Linux

- 如果发行版已提供Python3.10的软件包，则直接通过包管理器安装即可。
- 不会请看[这里](https://blog.csdn.net/weixin_43935402/article/details/121416812)
- ~~不会吧不会吧，你都用Linux还不会安装Python环境~~

#### 2.下载Bot

- 方法一：安装[Git](http://git-scm.com/)命令行工具，并使用以下命令克隆本仓库：
   ```
   git clone https://github.com/snowyfirefly/Liteyuki
   ```
- 方法二：或者点击下载zip，解压。

#### 3.安装适配器（以[go-cqhttp](https://docs.go-cqhttp.org/)为例）

- 这是一个适配器，通俗易懂来说就是一个qq客户端，它能接收消息并上报给Bot
- 转到[下载页面](https://github.com/Mrs4s/go-cqhttp/releases)，选择适合系统的版本进行下载
- 运行程序，根据提示进行配置，选择`反向websocket`通信方式，程序会生成`config.yml`，修改如下项即可

```yaml
# config.yml
# 请勿直接复制此内容到config.yml
# 默认情况下你只需要修改以下列出的项
# 端口号是一个0-65535的整数，自己选，但是必须和后面的nonebot端保持一致
account: # 账号相关
  uin: 114514 # QQ账号
  password: 'lts1919810' # 密码为空时使用扫码登录

servers:
  - ws-reverse:
      universal: ws://127.0.0.1:端口号/onebot/v11/ws
```

- 不清楚请见[go-cqhttp](https://docs.go-cqhttp.org/guide/quick_start.html)

#### 4.启动

- 启动Bot(Websocket服务端)，用命令行`python bot.py`启动，**不支持**`nb-cli`的`nb run`启动！
- 点击go-cqhttp生成的`bat`文件运行go-cqhttp(Websocket客户端)

## 配置

- 首次启动机器人时，会在根目录生成环境配置文件.env，大多数情况下，你只需要编辑以下内容

```
SUPERUSERS=[114514]     # Bot的超级用户，可以添加多个，拥有最高权限
NIKCKNAME=["轻雪"]       # Bot的通用昵称，用于呼唤Bot
PORT=11451              # Websocket服务端端口，此处和go-cqhttp配置相同的端口即可
```

- 给Bot发送`liteyuki`，若回复测试成功即为基础配置完成。

- 部分内置插件正常工作需要[手动配置](/docs/config.md)，如果你暂时不用这些功能可以忽略。

## 使用

- 请参阅[开发者使用手册](docs/usage.md)

## 常见问题

#### 0.更新频率

- 大多数情况下是每天一次，遇到无解bug请更新，若还是有bug请反馈。
- 给Bot发送`/update`（推荐）以更新，或者使用`git pull`

#### 1.机器人不响应群聊消息

- Bot加入群聊需要超级用户手动开启，私聊bot发送`群聊启用 <群号>`。
- Bot被风控

#### 2.Bot无法注册，收不到邮箱验证码

- Bot默认情况下发送`注册`可直接注册成功，用户可根据需求打开邮箱验证，防止滥用，详细请查看[手动配置](docs/config.md)。
- 邮箱配置无误后，若用户未收到验证码请检查垃圾邮件，90%的可能在那里面。

#### 3.其他问题

- 请提交issue
- 加入QQ群Liteyuki Studio[775840726](https://jq.qq.com/?_wv=1027&k=0UnuCqSh)，欢迎来玩


#### 4.捐赠
- 作者已经吃不起饭，睡大街了(doge)，如果你觉得此项目不错的话可以给作者一些鼓励，这将会是我继续维护的动力
- 微信-WeChat
  ![捐赠：微信](/docs/img/donate_wechat.png)
- 支付宝-Alipay
  ![捐赠：支付宝](/docs/img/donate_alipay.png)
