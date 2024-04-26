---
title: 功能命令
icon: comment
order: 2
category: 使用手册
---

## 功能插件命令

### **轻雪天气`liteyuki_weather`**

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
weather 天气, bind-city 绑定城市
```