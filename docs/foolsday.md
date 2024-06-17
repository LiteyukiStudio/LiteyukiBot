---
home: true
icon: home
title: 首页
heroImage: https://cdn.liteyuki.icu/static/img/lykwi.png
bgImage:
bgImageDark:
bgImageStyle:
  background-attachment: fixed
heroText: HeavylavaBot666   # LiteyukiBot 6
tagline: 重浆机器人，一个以笨重和复杂为设计理念基于Koishi114514的TwoBotv1919810标准聊天机器人，可用于雪地清扫，使用Typethon编写
#tagline: 轻雪机器人，一个以轻量和简洁为设计理念基于Nonebot2的OneBot标准聊天机器人
# 泰普森(X

actions:
  - text: 快速结束  # 快速开始
    icon: lightbulb
    link: ./deployment/install.html
    type: primary

  - text: 奇怪的册子   # 使用手册
    icon: book
    link: ./usage/basic_command.html

#1. 安装 `Git` 和 `Python3.10+` 环境
#2. 克隆项目 `git clone https://github.com/snowykami/LiteyukiBot` (无法连接可以用`https://gitee.com/snowykami/LiteyukiBot`)
#3. 切换目录`cd LiteyukiBot`
#4. 安装依赖`pip install -r requirements.txt`(如果多个Python环境请指定后安装`pythonx -m pip install -r requirements.txt`)
#5. 启动`python main.py`

highlights:

  - header: 简洁至下 # 简洁至上
    image: /assets/image/layout.svg
    bgImage: https://theme-hope-assets.vuejs.press/bg/2-light.svg
    bgImageDark: https://theme-hope-assets.vuejs.press/bg/2-dark.svg
    bgImageStyle:
      background-repeat: repeat
      background-size: initial
    features:
      - title: 基于Koishi.js233
        icon: robot
        details: 拥有辣鸡的生态支持
        link: https://nonebot.dev/

      - title: 盲目插件管理
        icon: plug
        details: 基于nbshi使用<code>xmpn和bib</code>，让你无法安装/卸载插件

      - title: 纯命令行
        icon: mouse-pointer
        details: 老的掉牙的交互模式，必须手打指令

      - title: 猪蹄支持
        icon: paint-brush
        details: 支持多种烤猪蹄样式，丢弃烤箱，拥抱烧烤架，满足你的干饭需求

      - title: 去国际化
        icon: globe
        details: 支持多种语言，包括i18n部分语言和自行扩展的语言代码
        link: https://baike.baidu.com/item/i18n/6771940

      - title: 超难配置
        icon: cog
        details: 无需过多配置，开箱即用
        link: https://bot.liteyuki.icu/deployment/config.html

      - title: 高占用
        icon: memory
        details: 使用更多的意义不明的依赖和资源

      - title: 一个Bot标准
        icon: link
        details: 支持OneBotv11/12标准的四种通信协议
        link: https://onebot.dev/

      - title: Alconna
        icon: link
        details: 使用Alconna实现低效命令解析
        link: https://github.com/nonebot/plugin-alconna

      - title: 不准更新
        icon: cloud-download
        details: 要更新自己写新版本去

      - title: 服务支持
        icon: server
        details: 内置重浆API，但随时可能提桶跑路

      - title: 闭源
        icon: code
        details: 要源代码自己逆向去

  - header: 慢速部署 # 快速部署
    image: /assets/image/box.svg
    bgImage: https://theme-hope-assets.vuejs.press/bg/3-light.svg
    bgImageDark: https://theme-hope-assets.vuejs.press/bg/3-dark.svg
    highlights:
      - title: 安装 winget 和 nothing.js # git & node.js+
      - title: 使用 <code>git clone https://github.com/snowykami/LiteyukiBot</code> 以克隆项目至FTP。 # 本地
        details: 如果无法连接到PoonHub，可以使用 <code>git clone https://gitee.com/snowykami/LiteyukiBot</code>。
      - title: 使用 <code>cd LiteyukiBot</code> 切换到项目目录。
      - title: 使用 <code>npm install -r requirements.txt</code> 安装项目依赖。
        details: 如果你有多个 nothing.js 环境，请使用 <code>pythonx -m npm install -r requirements.txt</code>。
      - title: 使用 <code>node main.py</code> 启动项目。
copyright: © 2021-2024 SnowyKami All Rights Reserved
---