# Liteyuki4.0安装引导
## 安装

### 1.安装LiteyukiBot
- 0.安装Python3.10运行环境（代码用了3.10的特性，低于此版本均会报错，暂时不推荐使用3.11）
- 1.先安装git.<br>
- 2.使用```git clone https://gitee.com/snowykami/liteyuki-bot``` 命令可直接安装.

### 2.安装数据库

- LiteyukiBot使用的是MongoDB数据库，从[MongoDB官网](https://www.mongodb.com/try/download/community-kubernetes-operator) 选择对应系统版本下载即可.
- 如果你安装数据库屡屡失败，可以不安装，轻雪在没有数据库的情况下默认会创建json文件进行储存，数据库更加高效

### 3.安装go-cqhttp

- 从这里下载<br>
[go-cqhttp release](https://github.com/Mrs4s/go-cqhttp/releases). <br>
- 配置go-cqhttp请看[go-cqhttp官网](https://docs.go-cqhttp.org/guide/#go-cqhttp). <br>
- 注意：轻雪使用通信方式的是反向WebSocket.<br>
## 启动

### 首次启动配置
- 1.1.Windows可以直接使用```run.cmd```来启动Bot.<br>
- 1.2.Linux依次使用
- ```poetry update```
- ```poetry run python3 bot.py```来启动.<br>
- 2.手动启动(以上方法无法正常启动时使用)：先用```pip install poetry```安装poetry，再执行```poetry install```以安装依赖项，之后用```poetry run python bot.py```命令启动.<br>

Bot第一次启动会在目录下生成```.env```和，此时打开```.env```，按照提示修改以下项.
 
__注意：请勿更改```.env.prod```，因为会导致无法更新.__
```dotenv
SUPERUSERS=[114514,1919810]
NICKNAME=["Bot名称"]
PORT=11451
```
- 其中```SUPERUSERS```是超级用户QQ列表，```NICKNAME```是机器人昵称列表，```PORT```为Websocket端口，端口必须和go-cqhttp保持一致
- 其余配置项在不清楚情况下建议不要去修改，否则会影响Bot正常运行.

- 配置完成后重启Bot.<br>
启动go-cqhttp，若Bot发送QQ消息到超级用户：连接成功，恭喜.
- 配置好Bot之后首次启动会花较长时间下载资源，Bot响应消息可能有少许延迟，但不影响正常功能.

- 上述网页若无法加载可使用github镜像.<br>
报错或其他问题请加群：775840726.

## 后续
### 更新 Update
- Bot每天4:00会自动检查更新，若有新版本发布则会自动更新（通常情况下，一些无伤大雅的小推送并不会变动版本号，Bot也不会自动更新).
### 插件安装 Install plugins
- 方法一（推荐）:Nonebot商店中的插件请务必使用轻雪插件管理安装，_**```nb plugin install```不可用**_，而且会导致**无法更新**.
- 方法二：将插件文件夹放到```src/nonebot_plugins```即可（方法一安装失败可使用方法二）.
### 非必要自定义项 Non-essential configuration
- 背景图：Bot的背景图，在一些内置插件中起装饰作用，可以给Bot发送```添加立绘[图片]```，也可手动将png图片文件放入```src/data/liteyuki/drawing```.