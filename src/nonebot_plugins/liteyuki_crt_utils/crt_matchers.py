from urllib.parse import quote

import aiohttp
from nonebot import require

from src.utils.event import get_user_id
from src.utils.base.language import Language
from src.utils.base.ly_typing import T_MessageEvent
from src.utils.base.resource import get_path
from src.utils.message.html_tool import template2image

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import UniMessage, on_alconna, Alconna, Args, Subcommand, Arparma, Option

crt_cmd = on_alconna(
    Alconna(
        "crt",
        Subcommand(
            "route",
            Args["start", str, "沙坪坝"]["end", str, "上新街"],
            alias=("r",),
            help_text="查询两地之间的地铁路线"
        ),
    )
)


@crt_cmd.assign("route")
async def _(result: Arparma, event: T_MessageEvent):
    # 获取语言
    ulang = Language(get_user_id(event))

    # 获取参数
    # 你也别问我为什么要quote两次，问就是CRT官网的锅，只有这样才可以运行
    start = quote(quote(result.other_args.get("start")))
    end = quote(quote(result.other_args.get("end")))

    # 判断参数语言
    query_lang_code = ""
    if start.isalpha() and end.isalpha():
        query_lang_code = "Eng"

    # 构造请求 URL
    url = f"https://www.cqmetro.cn/Front/html/TakeLine!queryYs{query_lang_code}TakeLine.action?entity.startStaName={start}&entity.endStaName={end}"

    # 请求数据
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            result = await resp.json()

    # 检查结果/无则终止
    if not result.get("result"):
        await crt_cmd.send(ulang.get("crt.no_result"))
        return

    # 模板传参定义
    templates = {
            "data"        : {
                    "result": result["result"],
            },
            "localization": ulang.get_many(
                "crt.station",
                "crt.hour",
                "crt.minute",
            )

    }

    # 生成图片
    image = await template2image(
        template=get_path("templates/crt_route.html"),
        templates=templates,
        debug=True
    )

    # 发送图片
    await crt_cmd.send(UniMessage.image(raw=image))
