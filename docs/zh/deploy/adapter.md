---
title: 适配器
order: 3
---

## **示例：与NoneBot对接的OneBot实现端配置**

生产环境中推荐反向WebSocket
不同的实现端给出的字段可能不同，但是基本上都是一样的，这里给出一个参考值

| 字段            | 参考值                          | 说明                                                                 |
|----------------|--------------------------------|----------------------------------------------------------------------|
| 协议            | 反向 WebSocket                  | 推荐使用反向 WebSocket 协议进行通信，即轻雪作为服务端运行。                   |
| 地址            | `ws://127.0.0.1:20216/onebot/v11/ws` | 地址取决于配置文件，本机默认为 `127.0.0.1:20216`。                           |
| AccessToken     | `""`                            | 如果你给轻雪配置了 `AccessToken`，请在此填写相同的值。                             |

> **注意**：要使用其他通信方式，请访问 [OneBot Adapter](https://onebot.adapters.nonebot.dev/) 获取详细信息。


## **其他**

轻雪不局限于OneBot适配器，你可以使用[NoneBot2支持的任何适配器](https://github.com/nonebot/)(链接指向nonebot的github主页)或使用轻雪讯息传递插件

例如:
- [Console Adapter](https://github.com/nonebot/adapter-console)
- [Mirai Adapter](https://github.com/nonebot/adapter-mirai)
等