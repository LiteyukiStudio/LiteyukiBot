<div align="center">

# Liteyuki Bot

### 基于[Nonebot](https://v2.nonebot.dev/)库和[go-cqhttp](https://docs.go-cqhttp.org/)的QQ机器人

</div>

## 简介

作者没有女朋友那段时间一个人过于寂寞，便写了这个bot来陪伴自己，顺便学习一些相关知识。使用了Nonebot库，继承了Nonebot的大部分优点，作者自己造了很多轮子和~~屎山~~。有相对简洁的插件管理功能，三种生产模式切换，功能强大的异步接口，其他插件可以基于这些接口开发。

## 安装

- 环境：Python3.10+

- 依赖：requirements.txt

- cqhttp自行下载

## 配置

部分插件需要配置特定数据

在项目根目录下面的data/g0.sjon最外层添加以下属性键值对

- kami.weather.key(去[和风天气](https://dev.qweather.com/)申请)

- kami.map.key(去[高德地图](https://console.amap.com/dev/key/app)申请)

