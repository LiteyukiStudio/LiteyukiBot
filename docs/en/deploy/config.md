---
title: Configurations
order: 2
---

# Configurations

LiteyukiBot supports `yaml`, `json`, and `toml` as configuration files, depending on your personal preference.

When you first run LiteyukiBot, it will generate `config.yml` and the `config` directory. You can modify the configuration items and restart LiteyukiBot. In most cases, you only need to modify
the `superusers` and `nickname` fields.

When starting, LiteyukiBot will load all configuration files in the project directory `config.yml/yaml/json/toml` and the `config` directory. You can create multiple configuration files in
the `config` directory, and LiteyukiBot will automatically merge these configuration files.

## **Basic Configuration**

```yaml
# NoneBot configuration
nonebot:
  command_start: [ "/", "" ] # Command prefix, if there is no "" empty command header, please enable alconna_use_command_start to ensure alconna parsing is normal
  host: 127.0.0.1 # Listening address, default is local, if you want to receive external requests, please fill in
  port: 20216 # Binding port
  nickname: [ "liteyuki" ]  # Bot nickname list
  superusers: [ "1919810" ]  # Superuser list
liteyuki:
  log_level: "INFO" # Log level
  log_icon: true # Whether to display the log level icon (some console fonts are not available)
  auto_report: true # Whether to automatically report problems to Liteyuki server
  auto_update: true # Whether to automatically update Liteyuki, check for updates at 4 am every day
  plugins: [ ] # Liteyuki plugin list
  plugin_dirs: [ ] # Liteyuki plugin directory list
```

## **Other configurations**

The following is the default value. If you need to customize it, please add it manually

```yaml
# Advanced configuration
nonebot:
  onebot_access_token: "" # OneBot access token
  default_language: "zh-CN" # Default language
  alconna_auto_completion: false # alconna auto completion
  safe_mode: false # Safe mode, if true, the bot will not load any plugins
  # other nonebot configurations
  custom_config_1: "custom_value1"
  custom_config_2: "custom_value2"

# development configuration
liteyuki:
  allow_update: true # Whether to allow Liteyuki to update
  debug: false  # Debug mode, if true, Liteyuki will output more detailed logs
  dev_mode: false # development mode, if true, Liteyuki will load all plugins in the development directory
...
```

```yaml

```

## **Example: Configuration of OneBot implementation side connected to NoneBot**

In production environments, it is recommended to use reverse WebSocket
The fields provided by different implementation sides may be different, but basically the same. Here is a reference value

| Fields      | Value                              | Description                                                                           |
|-------------|------------------------------------|---------------------------------------------------------------------------------------|
| protocol    | Reverse WebSocket                  | Liteyuki-NoneBot as server                                                            |
| address     | ws://127.0.0.1:20216/onebot/v11/ws | The address depends on the configuration file, the default is `                       |
| AccessToken | `""`                               | If you have configured `AccessToken` for Liteyuki, please fill in the same value here |  

- To use other communication methods, please visit [OneBot Adapter](https://onebot.adapters.nonebot.dev/) for detailed information

## **Other**

- Liteyuki is not limited to the OneBot adapter and NoneBot2. You can use any adapter supported by NoneBot2 or use the Liteyuki message delivery plugin
