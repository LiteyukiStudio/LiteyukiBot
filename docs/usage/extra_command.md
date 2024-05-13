---
title: 功能命令
icon: comment
order: 2
category: 使用手册
---

## 功能插件命令

### **轻雪天气`liteyuki_weather`**

查询实时天气，支持绑定城市，支持中英文城市名，支持多个关键词查询。

配置项

```yaml
weather_key: "" # 和风天气的天气key，会自动判断key版本
```

命令

```shell
weather <keywords...> # 查询目标地实时天气，例如："天气 北京 海淀", "weather Tokyo Shinjuku"
bind-city <keywords...> # 绑定查询城市，个人全局生效
```

命令别名

```shell
weather|天气
bind-city|绑定城市
```

***

### **统计信息`liteyuki_statistics`**

统计信息
命令

```shell
statistic message --duration <duration> --period <period> --group [current|group_id] --bot [current|bot_id] # 统计Bot接收到的消息
# duration: 统计时长，支持格式例如：1d2h3m4s
# period: 统计周期，支持格式同上
# group: 统计群组，支持current(当前群聊)和group_id
# bot: 统计Bot，支持current(当前bot)和bot_id
```

命令别名

```shell
statistic|stat  
message|m  
--duration|-d  
--period|-p  
--group|-g  
--bot|-b
current|c
```