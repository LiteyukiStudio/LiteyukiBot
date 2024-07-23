# npm update/upgrade
# npm search
# npm install/uninstall
# npm list
from nonebot import require

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import (
    on_alconna,
    Alconna,
    Args,
    MultiVar,
    Subcommand,
    Option
)

"""包管理器alc"""
npm_alc = on_alconna(
    aliases={"插件", "nonebot-plugin-manager"},
    command=Alconna(
        "npm",
        Subcommand(
            "list",
            Args["page", int, 1]["num", int, 10],
            alias={"ls", "列表", "列出"},
            dest="list installed plugins",
            help_text="列出已安装插件",
        ),
        Subcommand(
            "search",
            Args["keywords", MultiVar(str)],
            alias=["s", "搜索"],
            dest="search plugins",
            help_text="搜索本地商店插件，需自行更新",
        ),
        Subcommand(
            "install",
            Args["package_name", str],
            alias=["i", "安装"],
            dest="install plugin",
            help_text="安装插件",
        ),
        Subcommand(
            "uninstall",
            Args["package_name", str],
            alias=["u", "卸载"],
            dest="uninstall plugin",
            help_text="卸载插件",
        ),
        Subcommand(
            "update",
            alias={"更新"},
            dest="update local store index",
            help_text="更新本地索引库",
        ),
        Subcommand(
            "upgrade",
            Args["package_name", str],
            Option(
                "package_name",
                Args["package_name", str, None],  # Optional
            ),
            alias={"升级"},
            dest="upgrade all plugins without package name",
            help_text="升级插件",
        ),
    ),
)
