---
home: true
icon: home
title: 首页
heroImage: https://cdn.liteyuki.icu/static/img/logo.png
bgImage: 
bgImageDark: 
bgImageStyle:
  background-attachment: fixed
heroText: LiteyukiBot 6
tagline: 基于Nonebot2的OneBot标准聊天机器人，不仅仅局限于OneBot
actions:
  - text: 部署
    icon: lightbulb
    link: ./deployment/
    type: primary

  - text: 使用手册
    link: ./usage/

#1. 安装 `Git` 和 `Python3.10+` 环境
#2. 克隆项目 `git clone https://github.com/snowykami/LiteyukiBot` (无法连接可以用`https://gitee.com/snowykami/LiteyukiBot`)
#3. 切换目录`cd LiteyukiBot`
#4. 安装依赖`pip install -r requirements.txt`(如果多个Python环境请指定后安装`pythonx -m pip install -r requirements.txt`)
#5. 启动`python main.py`

highlights:
  - header: 快速部署
    image: /assets/image/box.svg
    bgImage: https://theme-hope-assets.vuejs.press/bg/3-light.svg
    bgImageDark: https://theme-hope-assets.vuejs.press/bg/3-dark.svg
    highlights:
      - title: 安装 Git 和 Python3.10+
      - title: 使用 <code>git clone https://github.com/snowykami/LiteyukiBot</code> 以克隆项目至本地。
        details: 如果无法连接到GitHub，可以使用 <code>git clone https://gitee.com/snowykami/LiteyukiBot</code>。
      - title: 使用 <code>cd LiteyukiBot</code> 切换到项目目录。
      - title: 使用 <code>pip install -r requirements.txt</code> 安装项目依赖。
        details: 如果你有多个 Python 环境，请使用 <code>pythonx -m pip install -r requirements.txt</code>。
      - title: 使用 <code>python main.py</code> 启动项目。
copyright: false
---