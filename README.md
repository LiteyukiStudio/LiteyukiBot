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
- 集成了上一代轻雪的优点和~~缺点~~
- 支持一切Onebot标准通信，后续会支持更多的平台

## 手动安装和部署

1. 安装`Git`和`Python3.10+`
2. 克隆项目到本地`git clone https://github.com/snowykami/LiteyukiBot`
3. 切换到轻雪目录`cd LiteyukiBot`
4. 安装依赖`pip install -r requirements.txt`
5. 启动`python main.py`

## 一键部署脚本(复制到本地保存执行)

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
echo python3 main.py > start.sh
chmod +x start.sh
echo Install finished! Please run "sh start.sh" to start the bot!
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
1. 使用`Lagrange.Core`，`Lagrange.Core`支持多种协议
2. 云崽的`icqq-plugin`和`ws-plugin`进行通信
3. `Go-cqhttp`（目前已经半死不活了）
4. 人工实现的`Onebot`协议，自己整一个WebSocket客户端，看着QQ的消息，然后给轻雪传输数据
### 推荐方案(Minecraft)
1. 我们有专门为Minecraft开发的服务器Bot，支持OnebotV11/12标准，详细请看[MinecraftOneBot](https://github.com/snowykami/MinecraftOnebot)

请先自行查阅文档，若有困难请联系相关开发者而不是Liteyuki的开发者

## 其他
- 有一个用`Nuitka`编译的C语言版本可用

## 鸣谢
