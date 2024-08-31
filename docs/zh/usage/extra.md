---
title: 功能命令
order: 2
---

# 功能插件命令

### **轻雪天气`liteyuki_weather`**

查询实时天气，支持绑定城市，支持中英文城市名，支持多个关键词查询。

配置项

```yaml
weather_key: "" # 和风天气的天气key，会自动判断key版本
```

命令

```shell
weather <keywords...> # Keywords为城市名，支持中英文
```
查询目标地实时天气，例如："天气 北京 海淀", "weather Tokyo Shinjuku"

```shell
bind-city <keywords...> # Keywords为城市名，支持中英文
```

绑定查询城市，个人全局生效

#### 命令别名

|   命令    | 别名     |
| :-------: | :------- |
|  weather  | 天气     |
| bind-city | 绑定城市 |

---

### **统计信息`liteyuki_statistics`**

统计信息
命令

```shell
statistic message --duration <duration> --period <period> --group [current|group_id] --bot [current|bot_id]
```

功能: 用于统计Bot接收到的消息, 统计周期为`period`, 统计时间范围为`duration`

|   参数   |                              格式                              |
| :------: | :------------------------------------------------------------: |
| duration | 使用通用日期简写: `1d`(天), `1h`(小时), `45m`(分钟), `14s`(秒) |
|  period  | 使用通用日期简写: `1d`(天), `1h`(小时), `45m`(分钟), `14s`(秒) |
|  group   |          `current` (当前群聊) 或 `group_id` (QQ群号)           |
|   bot    |                `current` (当前Bot) 或 `bot_id`                 |

#### 命令别名

|     命令     | 别名  |
| :----------: | :---: |
| `statistic`  | stat  |
|  `message`   |   m   |
| `--duration` |  -d   |
|  --period`   |  -p   |
|  `--group`   |  -g   |
|   `--bot`    |  -b   |
|  `current`   |   c   |
