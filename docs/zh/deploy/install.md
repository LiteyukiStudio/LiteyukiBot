---
title: 安装
order: 1
---

# 安装

## **常规部署**

### 安装基本环境

**Git 版本管理工具**
[Git](https://git-scm.com/download/)

**Python3.10+**
[Python3.10+](https://www.python.org/downloads/release/python-31010/)


### 克隆项目到本地，轻雪使用Git进行版本管理，该步骤为必要项

`git clone https://github.com/LiteyukiStudio/LiteyukiBot --depth=1`

> 若你不能访问Github，可以使用Liteyuki镜像：`https://git.liteyuki.icu/bot/app`

### 切换到Bot目录下

`cd LiteyukiBot`

> 如果存在文件夹缺失报错, 尝试使用绝对路径进行路径跳转

### 创建虚拟环境

`python -m venv venv`

> 如果出现相关虚拟环境错误, 建议查询 [Python Venv](https://docs.python.org/3/library/venv.html)


### 激活虚拟环境

Windows:
`.\venv\Scripts\activate`

> 出现`'activate' 不是内部或外部命令，也不是可运行的程序或批处理文件。`错误, 请使用完整路径激活虚拟环境

Linux:
`source venv/bin/activate`

> 如果出现`source: command not found`, 请使用完整路径激活虚拟环境


### 安装依赖

`pip install -r requirements.txt`

> 若出现`ERROR: Could not open requirements file: [Errno 2] No such file or directory`错误, 请检查是否在Bot目录下执行命令

> 若出现`ERROR: Could not build wheels for xx, which is required to install pyproject.toml-based projects`错误，请尝试使用手动命令安装相关依赖(虚拟环境下执行`pip install xx`，例如`pip install Pillow`)

### 启动Bot

`python main.py`

> 若出现`ModuleNotFoundError: No module named 'xx'`错误, 请尝试重新执行安装依赖步骤


## **使用Docker构建**

```bash
docker pull ghcr.io/liteyukistudio/liteyukibot:latest  # 每夜版镜像
```

> [!tip]
> Windows请使用项目绝对目录`/path/to/LiteyukiBot`代替`$(pwd)` <br>
> 若你修改了端口号请将`20216:20216`中的`20216`替换为你的端口号

## **装置要求**

- Windows系统版本推荐最低版本: `Windows 10 21H2` / `Windows Server 2019+`
>版本低于`Windows 10 21H2` 可能无法正常使用Bot, 建议升级系统版本或使用Docker部署

- Linux系统要支持Python3.10+，推荐`Ubuntu 20.04+`(~~别用你那b CentOS~~)

- CPU: 至少`1vCPU`

- 内存: Bot无其他插件会占用`300~500MB`，包括`chromium` 及 `node`等进程，其他插件占用视具体插件而定，建议`1GB`以上

- 硬盘: 至少`1GB`空间

> [!warning]
> 如果装置上有多个环境，请使用`path/to/python -m pip install -r requirements.txt`来安装依赖，`path/to/python`
> 为你的Python可执行文件路径

> [!warning]
> 轻雪的更新功能依赖Git，如果你没有安装Git直接下载源代码运行，你将无法使用更新功能(除非你闲的手动下载源代码更新轻雪~~)

#### 其他问题请移步至[答疑](./fandq)