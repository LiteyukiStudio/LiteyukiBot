<div align="center">
    <img src="https://nya.liteyuki.icu:809/static/img/liteyuki_icon.png" style="width: 30%; margin-top:10%;">
</div>
<div align=center>
    <h2>
        <font color="#d0e9ff">
            轻雪
        </font>
        <font color="#a2d8f4">
            5.0
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

## 一键自动部署脚本（测试）

#### Windows(先手动安装Git和Python并添加至环境变量，把脚本复制到部署目录的`*.bat`文件中)

```commandline
chcp 65001
echo 正在克隆项目...
git clone https://gitee.com/snowykami/liteyuki-bot
cd liteyuki-bot
echo 正在安装依赖...
pip install -r r.txt
echo python main.py > run.bat
echo pause >> run.bat
echo 启动脚本"run.bat"已创建，点击即可启动
pause
```

## 注意事项

1.请勿更改`.env`文件，若想添加自定义配置请**创建**`.env.prod`文件并在此文件更改

2.Bot会自动检测新版本，若出现新版本，可用`git pull`命令更新

## 使用手册

- [命令手册](docs/command.md)
- [资源包规范手册](docs/resource.md)
- [轻雪插件开发手册](docs/dev.md)

## 鸣谢

- html转图片使用的[kexue-z](https://github.com/kexue-z)的[nonebot-plugin-htmlrender](https://github.com/kexue-z/nonebot-plugin-htmlrender)插件的部分代码
- 重启方案用的[18870](https://github.com/18870)的[Nonebot-plugin-reboot](https://github.com/18870/nonebot-plugin-reboot)插件的部分代码
- JetBrains Pycharm和Vscode