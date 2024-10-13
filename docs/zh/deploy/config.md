---
title: 配置
order: 2
---
# 配置

轻雪支持`yaml`、`json`和`toml`作为配置文件，取决于你个人的喜好

首次运行后生成`config.yml`和`config`目录，你可修改配置项后重启轻雪，绝大多数情况下，你只需要修改`superusers`及`nickname`字段即可

启动时会加载项目目录下`config.yml/yaml/json/toml`和`config`目录下的所有配置文件，你可在`config`目录下创建多个配置文件，轻雪会自动合并这些配置文件

## **基础配置项**

```yaml
nonebot:
  # Nonebot机器人的配置，6.3.10版本后，NoneBot下配置已迁移至nonebot键下，不再使用外层配置，但是部分内容会被覆盖，请尽快迁移
  command_start: [ "/", "" ] # 指令前缀，若没有""空命令头，请开启alconna_use_command_start保证alconna解析正常
  host: 127.0.0.1 # 监听地址，默认为本机，若要接收外部请求请填写0.0.0.0
  port: 20216 # 绑定端口
  nickname: [ "liteyuki" ]  # 机器人昵称列表
  superusers: [ "1919810" ]  # 超级用户列表
liteyuki:
  # 写在外层的配置项将会被覆盖，建议迁移到liteyuki下
  log_level: "INFO" # 日志等级
  log_icon: true # 是否显示日志等级图标（某些控制台字体不可用）
  auto_report: true # 是否自动上报问题给轻雪服务器
  auto_update: true # 是否自动更新轻雪，每天4点检查更新
  plugins: [ ] # 轻雪插件列表
  plugin_dirs: [ ] # 轻雪插件目录列表
```

## **其他配置**

以下为默认值，如需自定义请手动添加

```yaml
# 高级NoneBot配置
nonebot:
  onebot_access_token: "" # 访问令牌，对公开放时建议设置
  default_language: "zh-CN" # 默认语言
  alconna_auto_completion: false # alconna是否自动补全指令，默认false，建议开启
  safe_mode: false # 安全模式，开启后将不会加载任何第三方NoneBot插件
  # 其他Nonebot插件的配置项
  custom_config_1: "custom_value1"
  custom_config_2: "custom_value2"

# 开发者选项
liteyuki:
  allow_update: true # 是否允许更新
  debug: false  # 轻雪调试，开启会自动重载Bot或者资源，其他插件自带的调试功能也将开启
  dev_mode: false # 开发者模式，开启后将会启动监视者，监视文件变化并自动重载

...
```

## **示例：与NoneBot对接的OneBot实现端配置**

生产环境中推荐反向WebSocket
不同的实现端给出的字段可能不同，但是基本上都是一样的，这里给出一个参考值

| 字段          | 参考值                                | 说明                               |
|-------------|------------------------------------|----------------------------------|
| 协议          | 反向WebSocket                        | 推荐使用反向ws协议进行通信，即轻雪作为服务端          |
| 地址          | ws://127.0.0.1:20216/onebot/v11/ws | 地址取决于配置文件，本机默认为`127.0.0.1:20216` |
| AccessToken | `""`                               | 如果你给轻雪配置了`AccessToken`，请在此填写相同的值 |
- 要使用其他通信方式请访问[OneBot Adapter](https://onebot.adapters.nonebot.dev/)获取详细信息

## **其他**

- 轻雪不局限于OneBot适配器，你可以使用NoneBot2支持的任何适配器或使用轻雪讯息传递插件
