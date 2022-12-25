# Liteyuki4.0
## 安装，直接开始

> ### 1.安装数据库

LiteyukiBot使用的是MongoDB数据库，从[MongoDB官网](https://www.mongodb.com/try/download/community-kubernetes-operator) 选择对应系统版本下载即可

> ### 2.安装LiteyukiBot

#### 方法一
使用```git clone https://gitee.com/snowykami/liteyuki-bot/tree/master``` 命令可直接安装

#### 方法二（推荐）
[轻雪安装器](../../../../TimeRainStarSky/TRSS_Liteyuki)

#### 方法三（更新极为麻烦）
点击```克隆/下载```下载zip文件解压即可

> ### 3.安装go-cqhttp

这个很重要，是Bot与QQ通信的桥梁，也是Bot的客户端
从这里下载

[go-cqhttp release](https://github.com/Mrs4s/go-cqhttp/releases)

[go-cqhttp release镜像](https://kgithub.com/Mrs4s/go-cqhttp/releases)

配置go-cqhttp请看[go-cqhttp官网](https://docs.go-cqhttp.org/guide/#go-cqhttp)

注意：轻雪使用通信方式的是反向WebSocket

## 开始运行

> ### 首次启动配置
Windows可以点击```run.cmd```来启动Bot

Bot第一次启动会在目录下生成```.env```和```pyproject.toml```，此时打开```.env```，按照提示修改以下项
```dotenv
SUPERUSERS=[114514,1919810]    # 超级用户的QQ号，多个用逗号分隔
NICKNAME=["小明", "轻雪"]   # Bot的昵称，用双引号包裹，多个用逗号分隔
COMMAND_START=[""]  # 这是命令前缀符号，轻雪默认没有前缀，可以根据需求添加```/```、```#```
PORT=11451  # Bot服务端运行端口，必须和go-cqhttp中配置的端口一致才可以连接
```
其余配置项在不清楚情况下建议不要去修改，否则会影响Bot正常运行

配置完成后重启Bot

启动go-cqhttp，若连接成功，恭喜
