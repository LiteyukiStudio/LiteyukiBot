---
title: 轻雪API
icon: code
order: 5
category: 使用指南
tag:
  - 配置
  - 部署
---

## **轻雪API**

轻雪API是轻雪运行中部分服务的支持，由`go`语言编写，例如错误反馈，图床链接等，目前服务由轻雪服务器提供，用户无需额外部署

接口

- `url` `https://api.liteyuki.icu`

- `POST` `/register` 注册一个Bot
    - 参数
        - `name` `string` Bot名称
        - `version` `string` Bot版本
        - `version_id` `int` Bot版本ID
        - `python` `string` Python版本
        - `os` `string` 操作系统
    - 返回
        - `code` `int` 状态码
        - `liteyuki_id` `string` 轻雪ID

- `POST` `/bug_report` 上报错误
    - 参数
        - `liteyuki_id` `string` 轻雪ID
        - `content` `string` 错误信息
        - `device_info` `string` 设备信息
    - 返回
        - `code` `int` 状态码
        - `report_id` `string` 错误ID

- `POST` `/upload_image` 图床上传
    - 参数
        - `image` `file` 图片文件
        - `liteyuki_id` `string` 轻雪ID,用于鉴权
    - 返回
        - `code` `int` 状态码
        - `url` `string` 图床链接