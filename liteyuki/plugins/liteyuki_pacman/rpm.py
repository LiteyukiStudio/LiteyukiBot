# 轻雪资源包管理器
import os

import yaml
from nonebot import require
from nonebot.permission import SUPERUSER

from liteyuki.internal.base.language import get_user_lang
from liteyuki.internal.base.ly_typing import T_Bot, T_MessageEvent
from liteyuki.internal.message.message import MarkdownMessage as md
from liteyuki.internal.base.resource import (ResourceMetadata, add_resource_pack, change_priority, check_exist, check_status, get_loaded_resource_packs, get_resource_metadata, load_resources, remove_resource_pack)

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Alconna, Args, on_alconna, Arparma, Subcommand


@on_alconna(
    aliases={"资源包"},
    command=Alconna(
        "rpm",
        Subcommand(
            "list",
            Args["page", int, 1]["num", int, 10],
            alias=["ls", "列表", "列出"],
        ),
        Subcommand(
            "load",
            Args["name", str],
            alias=["安装"],
        ),
        Subcommand(
            "unload",
            Args["name", str],
            alias=["卸载"],
        ),
        Subcommand(
            "up",
            Args["name", str],
            alias=["上移"],
        ),
        Subcommand(
            "down",
            Args["name", str],
            alias=["下移"],
        ),
        Subcommand(
            "top",
            Args["name", str],
            alias=["置顶"],
        ),
        Subcommand(
            "reload",
            alias=["重载"],
        ),
    ),
    permission=SUPERUSER
).handle()
async def _(bot: T_Bot, event: T_MessageEvent, result: Arparma):
    ulang = get_user_lang(str(event.user_id))
    reply = ""
    if result.subcommands.get("list"):
        loaded_rps = get_loaded_resource_packs()
        reply += f"{ulang.get('liteyuki.loaded_resources', NUM=len(loaded_rps))}\n"
        for rp in loaded_rps:
            btn_unload = md.btn_cmd(
                ulang.get("npm.uninstall"),
                f"rpm unload {rp.folder}"
            )
            btn_move_up = md.btn_cmd(
                ulang.get("rpm.move_up"),
                f"rpm up {rp.folder}"
            )
            btn_move_down = md.btn_cmd(
                ulang.get("rpm.move_down"),
                f"rpm down {rp.folder}"
            )
            btn_move_top = md.btn_cmd(
                ulang.get("rpm.move_top"),
                f"rpm top {rp.folder}"
            )
            # 添加新行
            reply += (f"\n**{md.escape(rp.name)}**({md.escape(rp.folder)})\n\n"
                      f"> {btn_move_up} {btn_move_down} {btn_move_top} {btn_unload}\n\n***")
        reply += f"\n\n{ulang.get('liteyuki.unloaded_resources')}\n"
        loaded_folders = [rp.folder for rp in get_loaded_resource_packs()]
        for folder in os.listdir("resources"):
            if folder not in loaded_folders and os.path.exists(os.path.join("resources", folder, "metadata.yml")):
                metadata = ResourceMetadata(
                    **yaml.load(
                        open(
                            os.path.join("resources", folder, "metadata.yml"),
                            encoding="utf-8"
                        ),
                        Loader=yaml.FullLoader
                    )
                )
                metadata.folder = folder
                metadata.path = os.path.join("resources", folder)
                btn_load = md.btn_cmd(
                    ulang.get("npm.install"),
                    f"rpm load {metadata.folder}"
                )
                # 添加新行
                reply += (f"\n**{md.escape(metadata.name)}**({md.escape(metadata.folder)})\n\n"
                          f"> {btn_load}\n\n***")
    elif result.subcommands.get("load") or result.subcommands.get("unload"):
        load = result.subcommands.get("load") is not None
        rp_name = result.args.get("name")
        r = False  # 操作结果
        if check_exist(rp_name):
            if load != check_status(rp_name):
                # 状态不同
                if load:
                    r = add_resource_pack(rp_name)
                else:
                    r = remove_resource_pack(rp_name)
                rp_meta = get_resource_metadata(rp_name)
                reply += ulang.get(
                    f"liteyuki.{'load' if load else 'unload'}_resource_{'success' if r else 'failed'}",
                    NAME=rp_meta.name
                )
            else:
                # 重复操作
                reply += ulang.get(f"liteyuki.resource_already_{'load' if load else 'unload'}ed", NAME=rp_name)
        else:
            reply += ulang.get("liteyuki.resource_not_found", NAME=rp_name)
        if r:
            btn_reload = md.btn_cmd(
                ulang.get("liteyuki.reload_resources"),
                f"rpm reload"
            )
            reply += "\n" + ulang.get("liteyuki.need_reload", BTN=btn_reload)
    elif result.subcommands.get("up") or result.subcommands.get("down") or result.subcommands.get("top"):
        rp_name = result.args.get("name")
        if result.subcommands.get("up"):
            delta = -1
        elif result.subcommands.get("down"):
            delta = 1
        else:
            delta = 0
        if check_exist(rp_name):
            if check_status(rp_name):
                r = change_priority(rp_name, delta)
                reply += ulang.get(f"liteyuki.change_priority_{'success' if r else 'failed'}", NAME=rp_name)
                if r:
                    btn_reload = md.btn_cmd(
                        ulang.get("liteyuki.reload_resources"),
                        f"rpm reload"
                    )
                    reply += "\n" + ulang.get("liteyuki.need_reload", BTN=btn_reload)
            else:
                reply += ulang.get("liteyuki.resource_not_found", NAME=rp_name)
        else:
            reply += ulang.get("liteyuki.resource_not_found", NAME=rp_name)
    elif result.subcommands.get("reload"):
        load_resources()
        reply = ulang.get(
            "liteyuki.reload_resources_success",
            NUM=len(get_loaded_resource_packs())
        )
    else:
        btn_reload = md.btn_cmd(
            ulang.get("liteyuki.reload_resources"),
            f"rpm reload"
        )
        btn_list = md.btn_cmd(
            ulang.get("liteyuki.list_resources"),
            f"rpm list"
        )
        reply += f"{btn_list}  \n  {btn_reload}"
    await md.send_md(reply, bot, event=event)
