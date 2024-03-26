<div align="center">
    <img src="https://cdn.liteyuki.icu/static/img/logo.png" style="width: 75%; margin-top:10%;" alt="a">
</div>
<div align=center>
    <h2>
        <font color="#d0e9ff">
            轻雪
        </font>
        <font color="#a2d8f4">
            6.0
        </font>
    </h2>
</div>
<div align=center><h4>轻量，高效，易于扩展</h4></div>

- 基于[Nonebot2]("https://github.com/nonebot/nonebot2")，有良好的生态支持
- 开箱即用，无需复杂配置
- 新的点击交互模式，拒绝手打指令
- 全新可视化`npm`包管理，支持一键安装插件
- 支持一切Onebot标准通信

## 1.安装和部署

1. 安装`Git`和`Python3.10+`
2. 克隆项目`git clone https://github.com/snowykami/LiteyukiBot`
3. 切换目录`cd LiteyukiBot`
4. 安装依赖`pip install -r requirements.txt`(如果多个Python环境请指定后安装`pythonx -m pip install -r requirements.txt`)
5. 启动`python main.py`

## 2. 配置

### 轻雪配置项(Nonebot插件配置项也可以写在此，与dotenv格式不同，应为小写)

如果不确定字段的含义，请不要修改（部分在自动生成配置文件中未列出，需手动添加）

```yaml
# 生成文件的配置项
command_start: [ "/", " " ] # 指令前缀
host: 127.0.0.1 # 监听地址
port: 20216 # 绑定端口
nickname: [ "liteyuki" ]  # 机器人昵称
superusers: [ "1919810" ]  # 超级用户
# 未列出的配置项（如要自定义请手动修改）
onebot_access_token: "" # Onebot访问令牌[具体请看](https://onebot.adapters.nonebot.dev/docs/guide/configuration)
default_language: "zh-CN" # 默认语言
log_level: "INFO" # 日志等级
log_icon: true # 是否显示日志等级图标（某些控制台不可用）
auto_report: true # 是否自动上报问题给轻雪服务器，仅包含硬件信息和运行软件版本

# 其他Nonebot插件的配置项
custom_config_1: "custom_value1"
...
```

### Onebot实现端配置

不同的实现端给出的字段可能不同，但是基本上都是一样的，这里给出一个参考值

| 字段          | 参考值                      | 说明                               |
|-------------|--------------------------|----------------------------------|
| 协议          | 反向WebSocket              | 轻雪默认使用反向ws协议进行通信，即轻雪作为服务端        |
| 地址          | ws://`addrss`/onebot/v11 | 地址取决于配置文件，本机默认为`127.0.0.1:20216` |
| AccessToken | `""`                     | 如果你给轻雪配置了`AccessToken`，请在此填写相同的值 |

## 3.其他

### 常见问题

- 设备上Python环境太乱了，pip和python不对应怎么办？
    - 请使用`/path/to/python -m pip install -r requirements.txt`来安装依赖，
      然后用`/path/to/python main.py`来启动Bot，
      其中`/path/to/python`是你要用来运行Bot可执行文件
- 为什么我启动后机器人没有反应？
    - 请检查配置文件的`command_start`或`superusers`，确认你有权限使用命令并按照正确的命令发送

- 怎么登录QQ等聊天平台
    - 你有这个问题说明你不是很了解这个项目，本项目不负责实现登录功能，只负责处理消息
      你需要使用Onebot标准的实现端来连接到轻雪并将消息上报给轻雪，下面已经列出一些推荐的实现端

#### 推荐方案(QQ)

1. [Lagrange.OneBot](https://github.com/KonataDev/Lagrange.Core)，目前点按交互目前仅支持Lagrange
2. [LiteLoaderQQNT OneBot](https://github.com/LLOneBot/LLOneBot)，基于NTQQ的Onebot实现
3. 云崽的`icqq-plugin`和`ws-plugin`进行通信
4. `Go-cqhttp`（目前已经半死不活了）
5. 人工实现的`Onebot`协议，自己整一个WebSocket客户端，看着QQ的消息，然后给轻雪传输数据

#### 推荐方案(Minecraft)

1. 我们有专门为Minecraft开发的服务器Bot，支持OnebotV11/12标准，详细请看[MinecraftOneBot](https://github.com/snowykami/MinecraftOnebot)

使用其他项目连接请先自行查阅文档，若有困难请联系对应开发者而不是Liteyuki的开发者

## 4.用户协议

1. 本项目遵循`MIT`协议，你可以自由使用，修改，分发，但是请保留原作者信息
2. 你可以选择开启`auto_report`(默认开启)，轻雪会收集运行环境的设备信息，通过安全的方式传输到轻雪服务器，用于统计运行时的设备信息，帮助我们改进轻雪，收集的数据包括但不限于：CPU，内存，插件信息，异常信息，会话负载(不含隐私部分)
3. 本项目不会收集用户的任何隐私信息，但请注意甄别第三方插件的安全性

## 5.鸣谢
