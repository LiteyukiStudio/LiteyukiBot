# Liteyuki4.0
## 安装

### 1.安装LiteyukiBot

#### **方法一（十分推荐）**
1.先安装git<br>
2.使用```git clone https://gitee.com/snowykami/liteyuki-bot/tree/master``` 命令可直接安装

#### **方法二（九分推荐）**
[轻雪安装器](../../../../TimeRainStarSky/TRSS_Liteyuki)<br>
注意：安装器自带更新功能，轻雪内置的更新功能需要git
#### **方法三（十分甚至九分不推荐，因为更新极为麻烦）**
点击```克隆/下载```下载zip文件解压即可<br> 
注意：此方法无法使用轻雪内置的更新功能

### 2.安装数据库

LiteyukiBot使用的是MongoDB数据库，从[MongoDB官网](https://www.mongodb.com/try/download/community-kubernetes-operator) 选择对应系统版本下载即可

### 3.安装go-cqhttp

从这里下载<br>
[go-cqhttp release](https://github.com/Mrs4s/go-cqhttp/releases) <br>
配置go-cqhttp请看[go-cqhttp官网](https://docs.go-cqhttp.org/guide/#go-cqhttp) <br>
这个很重要，是Bot与QQ通信的桥梁<br>
注意：轻雪使用通信方式的是反向WebSocket<br>
## 启动

### 首次启动配置
1.Windows可以点击```run.cmd```来启动Bot<br>
2.在```bot.py```所在目录下用```python bot.py```命令启动<br>
_注意：轻雪不支持```nb run```启动_

Bot第一次启动会在目录下生成```.env```和```pyproject.toml```，此时打开```.env```，按照提示修改以下项
```dotenv
SUPERUSERS=[114514,1919810]# 超级用户的QQ号，多个用逗号分隔
NICKNAME=["小明", "轻雪"]# Bot的昵称，用双引号包裹，多个用逗号分隔
COMMAND_START=[""]# 这是命令前缀符号，轻雪默认没有前缀，可以根据需求添加```/```、```#```
PORT=11451# Bot端运行端口，必须和go-cqhttp端中配置的端口一致才可以连接
```
其余配置项在不清楚情况下建议不要去修改，否则会影响Bot正常运行

配置完成后重启Bot<br>
启动go-cqhttp，若连接成功，恭喜

上述网页若无法加载可使用github镜像<br>
报错或其他问题请加群：775840726
