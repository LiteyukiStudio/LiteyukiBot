---
title: 配置
icon: cog
order: 2
category: 使用指南
tag:
  - 配置
  - 部署
---

### 轻雪配置项(Nonebot插件配置项也可以写在此，与dotenv格式不同，应为小写)

配置文件会在首次启动后生成，你可以在`config.yaml`中修改配置项后重启轻雪
如果不确定字段的含义，请不要修改（部分在自动生成配置文件中未列出，需手动添加）

```yaml
# 生成文件的配置项
command_start: [ "/", "" ] # 指令前缀，若没有""空命令头，请开启alconna_use_command_start保证alconna解析正常
host: 127.0.0.1 # 监听地址，默认为本机，若要对外开放请填写0.0.0.0或者你的公网IP
port: 20216 # 绑定端口
nickname: [ "liteyuki" ]  # 机器人昵称
superusers: [ "1919810" ]  # 超级用户

# 未列出的配置项（如要自定义请手动修改）
onebot_access_token: "" # 访问令牌，对公网开放时建议设置
default_language: "zh-CN" # 默认语言，支持i18n部分语言和自行扩展的语言代码
log_level: "INFO" # 日志等级
log_icon: true # 是否显示日志等级图标（某些控制台字体不可用）
auto_report: true # 是否自动上报问题给轻雪服务器，仅包含硬件信息和运行软件版本
fake_device_info: # 统计卡片显示的虚假设备信息，用于保护隐私
  cpu:
    brand: AMD
    cores: 16 # 物理核心数
    logical_cores: 32 # 逻辑核心数
    frequency: 3600 # CPU主频：MHz
  mem:
    total: 32768000000  # 内存总数：字节
alconna_use_command_start: false # alconna是否使用默认指令前缀，默认false
alconna_auto_completion: false # alconna是否自动补全指令，默认false，建议开启

# 其他Nonebot插件的配置项
custom_config_1: "custom_value1"
custom_config_2: "custom_value2"
...
```

### Onebot实现端配置

不同的实现端给出的字段可能不同，但是基本上都是一样的，这里给出一个参考值

| 字段          | 参考值                       | 说明                               |
|-------------|---------------------------|----------------------------------|
| 协议          | 反向WebSocket               | 推荐使用反向ws协议进行通信，即轻雪作为服务端          |
| 地址          | ws://`address`/onebot/v11/ws | 地址取决于配置文件，本机默认为`127.0.0.1:20216` |
| AccessToken | `""`                      | 如果你给轻雪配置了`AccessToken`，请在此填写相同的值 |

### 其他通信方式

- 实现端与轻雪的通信方式不局限为反向WebSocket，但是推荐使用反向WebSocket。
- 反向WebSocket的优点是轻雪作为服务端，可以更好的控制连接，适用于生产环境。
- 在某些情况下，你也可以使用正向WebSocket，比如你在开发轻雪插件时，可以使用正向WebSocket主动连接实现端
