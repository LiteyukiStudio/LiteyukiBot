---
title: liteyuki.plugin.model
order: 1
icon: laptop-code
category: API
---

### ***class*** `PluginType(Enum)`

插件类型枚举值

#### &emsp; ***attr*** `APPLICATION`

   Type: 'application'

#### &emsp; ***attr*** `SERVICE`

   Type: 'service'

#### &emsp; ***attr*** `IMPLEMENTATION`

   Type: 'implementation'

#### &emsp; ***attr*** `MODULE`

   Type: 'module'

#### &emsp; ***attr*** `UNCLASSIFIED`

   Type: 'unclassified'

### ***class*** `PluginMetadata(BaseModel)`

轻雪插件元数据，由插件编写者提供，name为必填项
Attributes:
----------

name: str
    插件名称
description: str
    插件描述
usage: str
    插件使用方法
type: str
    插件类型
author: str
    插件作者
homepage: str
    插件主页
extra: dict[str, Any]
    额外信息

### ***class*** `Plugin(BaseModel)`

存储插件信息

#### &emsp; ***attr*** `model_config`

   Type: {'arbitrary_types_allowed': True}

