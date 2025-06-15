<div align="center">

[//]: # (<img  src="https://cdn.liteyuki.org/logos/bot.svg" style="align-content: center; width: 50%; margin-top:10%;" alt="a">)
[![][banner]][liteyuki-link]
<h2><a href="https://bot.liteyuki.org"> <span style="color: #a2d8f4">轻雪</span> <span style="color: #d0e9ff">7</span></a></h2>
<h4> <span style="color: #a2d8f4">✨ 轻量，高效，易于扩展✨</span></h4>

[![][Liteyuki7.0]][liteyuki-link]
[![][Python3.12+]][python-link]
[![][Usage]][usage-link]
[![][Repo]][repo-link]
[![][Github]][github-link]
[![][LiteyukiLab]][liteyukilab-link]
![docs uptime](https://uptime.liteyuki.org/api/badge/8/uptime?labelPrefix=Docs+&style=for-the-badge)

**👇所有内容请访问👇**
[bot.liteyuki.org](https://bot.liteyuki.org)
</div>

> 受限的自由才是真正的自由

## 关于
开发中
访问[轻雪7.0](https://bot.liteyuki.org)主页获取更多信息

## 特点及优势

- 化繁为简, 加速开发
- 轻量级，快速启动
- 模块化设计，易于扩展

## 服务及支持(敬请期待)
- 提供Liteyuki Cloud官方的容器化托管服务(SaaS)，无需担心服务器问题


[Liteyuki7.0]: https://img.shields.io/badge/Liteyuki-7.0-blue?style=for-the-badge

[Python3.12+]: https://img.shields.io/badge/Python-3.12+-blue?style=for-the-badge

[Usage]: https://img.shields.io/badge/主页-文档-blue?style=for-the-badge

[Repo]: https://img.shields.io/badge/官方托管-仓库-blue?style=for-the-badge

[Github]: https://img.shields.io/badge/Github-仓库-blue?style=for-the-badge

[LiteyukiLab]: https://img.shields.io/badge/轻雪社区-官方-blue?style=for-the-badge



[python-link]:https://www.python.org/

[usage-link]:https://bot.liteyuki.org/

[liteyuki-link]:https://bot.liteyuki.org/

[repo-link]:https://git.liteyuki.org/bot/app

[github-link]:https://github.com/LiteyukiStudio/LiteyukiBot

[liteyukilab-link]:https://lab.liteyuki.org/@LiteyukiBot

[banner]: https://socialify.git.ci/LiteyukiStudio/LiteyukiBot/image?description=1&forks=1&issues=1&Plus&pulls=1&stargazers=1&theme=Auto&logo=https%3a%2f%2fcdn.liteyuki.org%2flogos%2fbot.svg

## 开发环境配置

1. 项目使用uv进行包管理，你也可以使用uv进行环境管理，[安装uv](https://docs.astral.sh/uv/#installation)

2. 进入项目目录使用uv同步环境和依赖

```bash
uv sync --all   # 安装包括dev和prod的所有依赖
```

3. VSCode扩展

- Python
- Mypy
- Ruff

4. 环境变量指定ENVIRONMENT=dev或prod或其他，然后加载.env.{}文件，环境变量