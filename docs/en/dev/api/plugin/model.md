---
title: liteyuki.plugin.model
order: 1
icon: laptop-code
category: API
---

### ***class*** `PluginType(Enum)`

插件类型枚举值

### &emsp; ***attr*** `APPLICATION: 'application'`

### &emsp; ***attr*** `SERVICE: 'service'`

### &emsp; ***attr*** `MODULE: 'module'`

### &emsp; ***attr*** `UNCLASSIFIED: 'unclassified'`

### &emsp; ***attr*** `TEST: 'test'`

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

### &emsp; ***attr*** `model_config: {'arbitrary_types_allowed': True}`

### ***var*** `APPLICATION = 'application'`



### ***var*** `SERVICE = 'service'`



### ***var*** `MODULE = 'module'`



### ***var*** `UNCLASSIFIED = 'unclassified'`



### ***var*** `TEST = 'test'`



### ***var*** `model_config = {'arbitrary_types_allowed': True}`



