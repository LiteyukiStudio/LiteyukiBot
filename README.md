<div align="center">
    <img src="https://ks.liteyuki.icu:809/static/img/liteyuki_icon.png" style="width: 30%; margin-top:10%;" alt="a">
</div>
<div align=center>
    <h2>
        <font color="#d0e9ff">
            轻雪
        </font>
        <font color="#a2d8f4">
            6.0
        </font>
    </h2>
</div>
<div align=center><h4>轻量，高效，易于扩展</h4></div>

- 基于[Nonebot2]("https://github.com/nonebot/nonebot2")，有良好的生态支持
- 集成了上一代轻雪的优点和~~缺点~~
- 支持Telegram/Github通信，后续会支持更多的平台

## 手动安装和部署

1.安装Git，使用命令`git clone https://gitee.com/snowykami/liteyuki-bot` 克隆项目至本地

2.切换到轻雪目录，使用`pip install -r r.txt`

3.`python main.py`！启动！

## 注意事项

1.尽可能不要去动配置文件，通过与bot交互进行配置即可，若仍然想自定义配置请在`config.yml`中修改

2.Bot会自动检测新版本，若出现新版本，可用`git pull`命令更新

## 鸣谢

- html转图片使用的[kexue-z](https://github.com/kexue-z)的[nonebot-plugin-htmlrender](https://github.com/kexue-z/nonebot-plugin-htmlrender)插件的部分代码
- 重启方案用的[18870](https://github.com/18870)的[Nonebot-plugin-reboot](https://github.com/18870/nonebot-plugin-reboot)插件的部分代码
- Lagrange.Core的测试环境支持