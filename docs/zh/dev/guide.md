---
title: 开发指南
order: 0
---
# 开发指南

## 如何开发
插件开发无需阅读本文档，请阅读[插件开发文档](./plugin)和[API 引用](./api/)。

如需往轻雪仓库提交代码，请阅读以下内容：
1. 首先[fork](https://github.com/LiteyukiStudio/LiteyukiBot/fork)一份轻雪仓库到你的个人/组织账户下。
2. 在你的仓库中进行开发。
3. 在你的仓库中创建一个新的分支，将你的代码提交到这个分支。
4. 在你的仓库中创建一个Pull Request，将你的分支合并到轻雪仓库的`main`分支。

参与开发默认你已经了解Python语言和轻雪框架的基本使用方法，如果是文档相关的开发，请确保你了解Markdown语法和基本前端知识。
出现冲突请与仓库维护者联系。

### 建议
- 开发过程中可以使用`mypy`, `flake8`, `black`等工具进行代码检查和格式化。
- 启用开发者模式，可以在`config.yml`中设置`dev_mode: true`，这样可以在控制台看到更多的调试信息。

## 规范化
- 代码请遵循[`PEP8`](https://pep8.org/)和[`Google Python Style Guide`](https://google.github.io/styleguide/pyguide.html)
- 此外，提交到轻雪仓库的代码，请遵循以下规范：
  - 请确保代码是可运行的，没有危害的。
  - 请确保代码的类型提示是正确的。
  - 请确保注释风格为[`Google Docstring`](https://google.github.io/styleguide/pyguide.html)或[`Liteyuki Docstring`](https://github.com/LiteyukiStudio/litedoc)(推荐)以保证Litedoc能够正确解析并生成文档。
  - 若有面向普通用户部分，请确保文档是完善的(每种语言都有对应的文档)。
- 文档请遵循[`Markdown`](https://www.markdownguide.org/)语法，并且支持vitepress相关内容：
  - 编辑文档时每个语言的文档都要修订。
  - 请确保文档内的链接是正确的，不要出现无法访问的链接。
  - 请确保**用户文档**是通俗易懂的，**开发文档**是详细的。

## 最后
- 本项目是一个非盈利的开源项目，我们欢迎任何人参与开发，你的贡献将会使轻雪变得更好。