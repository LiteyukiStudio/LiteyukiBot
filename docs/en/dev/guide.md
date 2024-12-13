---
title: Development Guide
order: 0
---

<script setup>
import ContributorBar from '../../components/ContributorBar.vue'
</script>


# Development Guide

## How to Develop
Please read the [Plugin Development](./plugin) and [API Reference](./api/) documents if you are developing a plugin.

If you need to submit code to the Liteyuki repository, please read the following:
1. First [fork](https://github.com/LiteyukiStudio/LiteyukiBot/fork) a copy of the Liteyuki repository to your personal/organization account.
2. Develop in your repository.
3. Create a new branch in your repository and submit your code to this branch.
4. Create a Pull Request in your repository to merge your branch into the `main` branch of the Liteyuki repository.

- Participation in development assumes that you are already familiar with the basic usage of the Python language and the Liteyuki framework. 
- If you are developing documentation, please ensure that you are familiar with Markdown syntax and basic front-end knowledge.
- Contact the repository maintainer in case of conflicts.

### Suggestions
- During development, you can use tools such as `mypy`, `flake8`, and `black` for code checking and formatting.
- Enable developer mode by setting `dev_mode: true` in `config.yml` to see more debugging information in the console.

## Project Structure
- `main.py`: Bot entry file
- `liteyuki`: Framework directory (liteyukibot)
- `src`: Bot application source code directory
  - `liteyuki_plugins`: Liteyuki plugin directory
  - `nonebot_plugins`: Nonebot plugin directory
  - `resources`: Built-in resource packs directory
  - `utils`: Utility directory
- `tests`: Unit test directory
- `docs`: Documentation directory
  - `en`: English documentation
  - `zh`: Chinese documentation
- `docker`: Docker related content directory

The `liteyuki` framework is included in the `LiteyukiBot` application, so this project is both the `LiteyukiBot` application repository and the `liteyuki` framework repository.

The `src` directory is the application part, please develop business logic in this directory. `liteyuki_plugins` and `nonebot_plugins` directories are plugin directories, please develop plugins in these directories.


## Standardization
- Code should follow [`PEP8`](https://pep8.org/) and [`Google Python Style Guide`](https://google.github.io/styleguide/pyguide.html).
- In addition, code submitted to the Liteyuki repository should follow the following guidelines:
  - Ensure that the code is runnable and harmless.
  - Ensure that the type hints in the code are correct.
  - Ensure that the comment style is [`Google Docstring`](https://google.github.io/styleguide/pyguide.html) or 
  [`Liteyuki Docstring`](https://github.com/LiteyukiStudio/litedoc?tab=readme-ov-file#liteyuki-docstring)(recommended) to ensure that Litedoc can parse and generate documentation correctly.
  - Strings should be enclosed in double quotes `"` as much as possible, and single quotes `'` should be used when nesting strings.
  - If there is a part for ordinary users, ensure that the documentation is complete (each language has corresponding documentation).
- commit message should follow the following guidelines:
  - You should commit the code after completing a feature or fixing a bug, and not mix the code of multiple features or bugs together.
  - We use gitmoji to mark the type of commit, such as `:sparkles:` for introducing new features, `:bug:` for fixing bugs, etc., please refer to [gitmoji](https://gitmoji.dev/) for details.
  - The format of the commit message is `<emoji> [type:] <message>`, such as `:sparkles: feat: add new field to event`,
  where the type field is the type of commit, not much is required, but please fill in as much as possible; the message field is a brief description, in summary, what you did.
  - There is no restriction on the language of the commit message, and bilingual use is possible if conditions permit.
- The documentation should follow [`Markdown`](https://www.markdownguide.org/) syntax and support vitepress-related content:
  - Revise the documentation for each language when editing.
  - Ensure that the links in the document are correct and do not lead to inaccessible links.
  - Ensure that the **User Documentation** is easy to understand and the **Development Documentation** is detailed.

## Finally
- This project is a non-profit open-source project, and we welcome anyone to participate in development. Your contributions will make Liteyuki better.


<ContributorBar />