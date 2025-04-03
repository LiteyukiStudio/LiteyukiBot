---
title: 配置
order: 2
---
# 配置

## 轻雪配置文件说明

轻雪支持 `.yaml`、`.json` 和 `.toml` 三种文件类型作为配置文件, 您可以根据个人喜好选择使用

### 配置文件生成

首次运行轻雪后，会生成以下文件和目录结构:

```
./
├── config.yml # 默认生成的配置文件
└── config/ # 配置目录，可包含多个配置文件
    └── file1.yaml # 示例配置文件1
    └── file2.json # 示例配置文件2
    └── file3.toml # 示例配置文件3
```


### 配置文件修改

您可以修改生成的 `config.yml` 文件或在 `config` 目录下添加新的配置文件

绝大多数情况下，您只需要修改以下字段:

- `superusers`：超级用户列表
- `nickname`：昵称配置

修改完成后，重启轻雪以应用新的配置

### 配置文件加载

启动轻雪时，会加载项目目录下以下文件和 `config` 目录下的所有配置文件:

- `config.yml`
- `config.yaml`
- `config.json`
- `config.toml`

轻雪会自动合并 `config` 目录下的所有配置文件

这意味着您可以在 `config` 目录下创建多个配置文件, 轻雪会将它们的内容合并为一个完整的配置

## 示例配置文件

### **基础配置项**

> 请注意, 文档中的配置代码是被拆分的, 实际上为一个配置文件(`config.yml`)，此处仅为方便阅读拆分

**Nonebot配置**
```yaml
nonebot:
  # Nonebot机器人的配置，6.3.10版本后，NoneBot下配置已迁移至nonebot键下，不再使用外层配置，但是部分内容会被覆盖，请尽快迁移
  command_start: [ "/", "" ]  # 指令前缀，若没有""空命令头，请开启alconna_use_command_start保证alconna解析正常
  host: 127.0.0.1             # 监听地址，默认为本机，若要接收外部请求请填写0.0.0.0
  port: 20216                 # 绑定端口
  nickname: [ "liteyuki" ]    # 机器人昵称列表
  superusers: [ "1919810" ]   # 超级用户列表
```

**Liteyuki配置**
```yaml
liteyuki:
  # 写在外层的配置项将会被覆盖，建议迁移到liteyuki下
  log_level: "INFO"          # 日志等级
  log_icon: true             # 是否显示日志等级图标（某些控制台字体不可用）
  auto_report: true          # 是否自动上报问题给轻雪服务器
  auto_update: true          # 是否自动更新轻雪，每天4点检查更新
  plugins: [ ]               # 轻雪插件列表
  plugin_dirs: [ ]           # 轻雪插件目录列表
```

## **其他配置**

以下为默认值，如需自定义请手动添加

```yaml
# 高级NoneBot配置
nonebot:
  onebot_access_token: ""         # 访问令牌，对公开放时建议设置
  default_language: "zh-CN"       # 默认语言
  alconna_auto_completion: false  # alconna是否自动补全指令，默认false，建议开启
  safe_mode: false                # 安全模式，开启后将不会加载任何第三方NoneBot插件

  # 其他Nonebot插件的配置项
  custom_config_1: "custom_value1"
  custom_config_2: "custom_value2"
```

```yaml
# 开发者选项
liteyuki:
  allow_update: true         # 是否允许更新
  debug: false               # 轻雪调试，开启会自动重载Bot或者资源，其他插件自带的调试功能也将开启
  dev_mode: false            # 开发者模式，开启后将会启动监视者，监视文件变化并自动重载
# ...其他配置项...
```
