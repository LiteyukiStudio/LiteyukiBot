---
title: 安装
icon: download
order: 1
category: 使用指南
tag:
  - 安装
---

### 设备要求
- Windows系统版本最低`Windows10+`/`Windows Server 2019+`
- Linux系统要支持Python3.10+，推荐`Ubuntu 20.04+`/`CentOS 8+`
- CPU: 至少`1vCPU`
- 内存: Bot无其他插件会占用`100MB`，其他插件占用视具体插件而定，建议`1GB`以上
- 硬盘: 至少`1GB`空间
- GPU: 原生轻雪无需GPU，某些插件需要GPU支持，例如AI绘画之类的，具体查看插件文档

### 开始安装
1. 安装 `Git` 和 `Python3.10+` 环境
2. 克隆项目 `git clone https://github.com/snowykami/LiteyukiBot` (无法连接可以用`https://gitee.com/snowykami/LiteyukiBot`)
3. 切换目录`cd LiteyukiBot`
4. 安装依赖`pip install -r requirements.txt`(如果多个Python环境请指定后安装`pythonx -m pip install -r requirements.txt`)
5. 启动`python main.py`

#### 想在Linux命令行中拥有更好的体验？试试[TRSS_Liteyuki轻雪机器人管理脚本](https://timerainstarsky.github.io/TRSS_Liteyuki/)，该功能仅供参考，不是LiteyukiBot官方提供的功能
