<div align="center">
    <img src="https://ks.liteyuki.icu:809/static/img/liteyuki_icon.png" style="width: 30%; margin-top:10%;" alt="a">
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

## 1.手动安装和部署

1. 安装`Git`和`Python3.10+`
2. 克隆项目`git clone https://github.com/snowykami/LiteyukiBot`
3. 切换目录`cd LiteyukiBot`
4. 安装依赖`pip install -r requirements.txt`(如果多个Python环境请指定后安装`pythonx -m pip install -r requirements.txt`)
5. 启动`python main.py`

## 1.一键部署脚本

#### 提前部署好`Python3.10+`环境和`Git`环境

#### Windows

```bash
chcp 65001
git clone https://github.com/snowykami/LiteyukiBot
cd LiteyukiBot
pip install -r requirements.txt
echo python3 main.py > start.bat
echo Install finished! Please click "start.bat" to start the bot!
```

#### Linux

```bash
git clone https://github.com/snowykami/LiteyukiBot
cd LiteyukiBot
pip install -r requirements.txt
echo python3.10 main.py > start.sh
chmod +x start.sh
echo Install finished! Please run "sh start.sh" to start the bot!
```

## 2. 配置项(Nonebot插件配置项也可以写在此)

```yaml
# 建议修改的配置项目
command_start: [ "/", " " ] # 指令前缀
host: 127.0.0.1 # 反向监听地址
port: 20216 # 绑定端口
nickname: [ "liteyuki" ]  # 机器人昵称
superusers: [ "1919810" ]  # 超级用户
show_icon: true # 是否显示日志等级图标（某些控制台不可用）

# 下面是不建议修改，且默认没有列出的配置项，除非你有特殊需求
log_level: "INFO" # 日志等级

# 其他Nonebot插件的配置项
custom_config_1: "custom_value1"
...
```

## 注意事项

- 首次启动会提醒用户注册超级用户

- Bot会自动检测新版本，若出现新版本，可用`git pull`命令更新

### Onebot实现端配置

| 字段 | 参考值                           | 说明                        |
|----|-------------------------------|---------------------------|
| 协议 | 反向WebSocket                   | 轻雪默认使用反向ws协议进行通信，即轻雪作为服务端 |
| 地址 | ws://`host`:`port`/onebot/v11 | 地址取决于配置文件，默认为`20216`端口    |

### 推荐方案(QQ)

1. 使用`Lagrange.OneBot`，点按交互目前仅支持`Lagrange.OneBot`，详细请看[Lagrange.OneBot]()
2. 云崽的`icqq-plugin`和`ws-plugin`进行通信
3. `Go-cqhttp`（目前已经半死不活了）
4. 人工实现的`Onebot`协议，自己整一个WebSocket客户端，看着QQ的消息，然后给轻雪传输数据

### 推荐方案(Minecraft)

1. 我们有专门为Minecraft开发的服务器Bot，支持OnebotV11/12标准，详细请看[MinecraftOneBot](https://github.com/snowykami/MinecraftOnebot)

请先自行查阅文档，若有困难请联系相关开发者而不是Liteyuki的开发者

## 其他

- 有一个用`Nuitka`编译的C语言版本可用

## 用户协议
1. 本项目遵循`MIT`协议，你可以自由使用，修改，分发，但是请保留原作者信息
2. 轻雪会收集使用者的设备信息，通过安全的方式传输到服务器，用于统计用户数量和设备信息，进行优化
3. 本项目不会收集用户的任何隐私信息，但请注意甄别第三方插件的安全性

## 鸣谢
