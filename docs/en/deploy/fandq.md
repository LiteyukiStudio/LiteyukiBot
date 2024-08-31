---
title: FAQ
order: 3
---
# FAQ

## **Frequently Asked Questions**

- There are too many python interpreters on my computer, how do I know which one to use?
    - You can specify which python interpreter to use by using the full path to the python executable, for example, `/path/to/python main.py`
    - Use virtual environments to avoid conflicts between different python interpreters

- Why does the bot not respond after I start it?
    - Please check the configuration file `command_start` or `superusers`, make sure you have permission to use the command and send it correctly
    - Make sure the command header does not conflict with `nickname{}`, for example, a command is `help`, but the `Bot` nickname has a `help`, then it will be parsed as a nickname instead of a command

- Update Liteyuki failed, error `InvalidGitRepositoryError`
    - Please install `Git` correctly and deploy Liteyuki using cloning instead of direct download

- How to log in to chat platforms such as Telegram?
    - If you have this question, it means you don't know much about this project. 
      This project does not implement the login function, only the message processing and response. 
      The login function is provided by the implementation side (protocol side). The implementation side itself does not handle response logic. 
      It processes and reports messages to Liteyuki according to the OneBot standard. 
      You need to use an implementation side that complies with the OneBot standard to connect to Liteyuki and report messages to Liteyuki. 
      Some recommended implementation sides have been listed below

- `Playwright` installation failed
    - Enter `playwright install` to install the browser

- Some plugins report errors after installation and cannot be started
    - Please refer to the plugin documentation first, confirm that the necessary configuration items of the plugin are intact, 
      and if the problem persists, please contact the plugin author or start Liteyuki in safe mode `safe_mode: true`. 
      In safe mode, you can use `npm uninstall` to uninstall problematic plugins

## Other questions

- Join chat group[775840726](http://qm.qq.com/cgi-bin/qm/qr?_wv=1027&k=SzmDYbfR6jY94o9KFNon7AwelRyI6M_u&authKey=ygeBdEmdFNyCWuNR4w0M1M8%2B5oDg7k%2FDfN0tzBkYcnbB%2FGHNnlVEnCIGbdftsnn7&noverify=0&group_code=775840726)
- If you don't have a QQ account, you can [submit an issue on GitHub](https://github.com/LiteyukiStudio/LiteyukiBot/issues/new?assignees=&labels=&projects=&template=%E9%97%AE%E9%A2%98%E5%8F%8D%E9%A6%88.md&title=)

## **Recommended Solution(QQ)**

1. [Lagrange.OneBot](https://github.com/KonataDev/Lagrange.Core), based on `Lagrange.Core`, a Linux QQ implementation, supports OneBotv11 protocol
2. [LLOneBot](https://github.com/LLOneBot/LLOneBot), a plugin for `Liteloader NTQQ`, supports OneBotv11 protocol
3. [OpenShamrock](https://github.com/whitechi73/OpenShamrock), based on Lsposed, supports kritor protocol
4. [TRSS-Yunzai](https://github.com/TimeRainStarSky/Yunzai), based on `Node.js`, supports OneBotv11 protocol
5. [go-cqhttp](https://github.com/Mrs4s/go-cqhttp)，A QQ Client based on `go`, supports OneBotv11 protocol
6. [Gensokyo](https://github.com/Hoshinonyaruko/Gensokyo), use QQ protocol

## **Recommended Solution(Minecraft)**

1. [MinecraftOneBot](https://github.com/snowykami/MinecraftOnebot), We develop a Minecraft server chat bot

Other project encountered issues, please prioritize the documentation and issues of the project itself, don't ask LiteyukiBot developers

## **Acknowledgements**

- [Nonebot2](https://nonebot.dev) provides the underlying framework
- [nonebot-plugin-alconna](https://github.com/ArcletProject/nonebot-plugin-alconna) provides the command parser
- [MiSans](https://hyperos.mi.com/font/zh/)，[MapleMono](https://gitee.com/mirrors/Maple-Mono) provides the font
